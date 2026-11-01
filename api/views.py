import time
from datetime import timedelta
from .models import User, Question, Announcement, GameResult, PromoCode, PromoRedemption, SolvedQuestion
from django.db import IntegrityError, transaction
from django.db.models import F, Sum, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import (
    api_view, permission_classes, authentication_classes, throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, Question, Announcement, GameResult, SyncSection
from .serializers import (
    UserSerializer, RegisterSerializer, MeUpdateSerializer,
    QuestionPublicSerializer, AnswerSerializer, ResultSerializer,
    AnnouncementSerializer,
)

# ================= SOZLAMALAR (xohlaganingizcha o'zgartiring) =================

# Kunlik bonus: 1-kundan 7-kungacha (coin, xp)
BONUS_REWARDS = [(10, 10), (15, 15), (20, 20), (25, 25), (30, 30), (40, 40), (60, 60)]

# Test savoliga to'g'ri javob uchun
QUESTION_COINS = 10
QUESTION_XP = 12

# Bir kunda o'yin va testlardan olish mumkin bo'lgan eng ko'p coin (bonus kirmaydi)
DAILY_COIN_CAP = 600

# Bitta natija yuborishda beriladigan eng ko'p mukofot
GAME_LIMITS = {
    "history_puzzle": {"coins": 110, "xp": 130},
    "memory":         {"coins": 80,  "xp": 100},
    "millionaire":    {"coins": 150, "xp": 180},
    "tugofwar":       {"coins": 60,  "xp": 80},
    "multiplayer":    {"coins": 60,  "xp": 80},
    "boardgames":     {"coins": 60,  "xp": 80},
    "pomodoro":       {"coins": 40,  "xp": 50},
}


# ================= YORDAMCHI FUNKSIYALAR =================

def todays_coins(user):
    """Bugun o'yin va testlardan topilgan coin."""
    today = timezone.localdate()
    total = GameResult.objects.filter(
        user=user, created_at__date=today
    ).aggregate(s=Sum("coins_earned"))["s"]
    return total or 0


def apply_reward(user, coins, xp):
    """Coin/XP ni xavfsiz (bir vaqtda kelgan so'rovlarda ham to'g'ri) qo'shadi."""
    User.objects.filter(pk=user.pk).update(
        coins=F("coins") + coins, xp=F("xp") + xp
    )
    user.refresh_from_db(fields=["coins", "xp"])


def bonus_state(user):
    """(bugun, olish mumkinmi, qaysi kun) ni qaytaradi."""
    today = timezone.localdate()
    last = user.last_bonus_date
    if last == today:
        return today, False, user.bonus_streak
    if last == today - timedelta(days=1):
        return today, True, user.bonus_streak % 7 + 1
    return today, True, 1


# ================= ENDPOINTLAR =================

# HEAD ham ruxsat: UptimeRobot kabi monitorlar HEAD yuboradi (aks holda 405 chiqadi)
@api_view(["GET", "HEAD"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    return Response({"status": "ok", "message": "8-sinf gaming portal API ishlayapti"})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=201,
        )


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class LeaderboardView(APIView):
    def get(self, request):
        by = request.query_params.get("by", "xp")
        field = "coins" if by == "coins" else "xp"

        students = User.objects.filter(role=User.Role.STUDENT)
        top = (
            students.annotate(badge_count=Count("badges"))
            .order_by(f"-{field}", "id")[:50]
        )
        rows = [
            {
                "rank": i + 1,
                "id": u.id,
                "name": u.get_full_name() or u.username,
                "school_class": u.school_class,
                "xp": u.xp,
                "coins": u.coins,
                "level": u.level,
                "badge_count": u.badge_count,
            }
            for i, u in enumerate(top)
        ]

        my_value = getattr(request.user, field)
        my_rank = students.filter(**{f"{field}__gt": my_value}).count() + 1

        return Response(
            {"by": field, "total_students": students.count(), "my_rank": my_rank, "results": rows}
        )


class SubjectListView(APIView):
    def get(self, request):
        data = (
            Question.objects.filter(is_active=True)
            .values("subject")
            .annotate(count=Count("id"))
            .order_by("subject")
        )
        return Response(list(data))


class QuestionListView(APIView):
    """GET /api/questions/?subject=Matematika&count=10
    Faqat foydalanuvchi hali to'g'ri yechmagan savollarni qaytaradi."""

    def get(self, request):
        base = Question.objects.filter(is_active=True)
        subject = request.query_params.get("subject")
        if subject:
            base = base.filter(subject=subject)

        total = base.count()
        remaining = base.exclude(solved_by__user=request.user)
        try:
            count = int(request.query_params.get("count", 10))
        except ValueError:
            count = 10
        count = max(1, min(count, 30))

        questions = list(remaining.order_by("?")[:count])
        return Response(
            {
                "total": total,
                "solved": total - remaining.count(),
                "all_done": total > 0 and len(questions) == 0,
                "questions": QuestionPublicSerializer(questions, many=True).data,
            }
        )


class AnswerView(APIView):
    """Javobni SERVER tekshiradi. Mukofot har savol uchun faqat bir marta beriladi."""

    def post(self, request):
        s = AnswerSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        question = get_object_or_404(Question, pk=s.validated_data["question_id"], is_active=True)
        correct = s.validated_data["selected_index"] == question.correct_index

        coins = xp = 0
        cap_reached = False

        if correct:
            room = max(0, DAILY_COIN_CAP - todays_coins(request.user))
            if room == 0:
                cap_reached = True  # savol yechilgan deb belgilanmaydi, ertaga qayta chiqadi
            else:
                with transaction.atomic():
                    _, created = SolvedQuestion.objects.get_or_create(
                        user=request.user, question=question
                    )
                    if created:
                        coins = min(QUESTION_COINS, room)
                        xp = QUESTION_XP
                        cap_reached = coins < QUESTION_COINS
                        GameResult.objects.create(
                            user=request.user, game="tests", score=1,
                            coins_earned=coins, xp_earned=xp,
                        )
                        apply_reward(request.user, coins, xp)

        return Response(
            {
                "correct": correct,
                "correct_index": question.correct_index,
                "explanation": question.explanation,
                "coins_earned": coins,
                "xp_earned": xp,
                "daily_cap_reached": cap_reached,
                "user": UserSerializer(request.user).data,
            }
        )


class ResultView(APIView):
    """Tarix Puzzle, Xotira, Millioner kabi o'yinlar natijasini qabul qiladi."""

    def post(self, request):
        s = ResultSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # Noma'lum o'yin nomi kelsa, 500 emas, tushunarli 400 qaytadi
        limits = GAME_LIMITS.get(data["game"])
        if limits is None:
            return Response({"detail": "Noma'lum o'yin turi."}, status=400)

        coins = max(0, min(data["coins_earned"], limits["coins"]))
        xp = max(0, min(data["xp_earned"], limits["xp"]))

        room = max(0, DAILY_COIN_CAP - todays_coins(request.user))
        coins = min(coins, room)
        if room == 0:
            xp = 0

        with transaction.atomic():
            GameResult.objects.create(
                user=request.user, game=data["game"], score=data["score"],
                coins_earned=coins, xp_earned=xp,
            )
            apply_reward(request.user, coins, xp)

        return Response(
            {
                "coins_earned": coins,
                "xp_earned": xp,
                "daily_cap_reached": room == 0 or coins < data["coins_earned"],
                "user": UserSerializer(request.user).data,
            },
            status=201,
        )


class BonusStatusView(APIView):
    def get(self, request):
        _, can_claim, day = bonus_state(request.user)
        return Response(
            {
                "can_claim": can_claim,
                "day": day,
                "rewards": [
                    {"day": i + 1, "coins": c, "xp": x}
                    for i, (c, x) in enumerate(BONUS_REWARDS)
                ],
            }
        )


class BonusClaimView(APIView):
    def post(self, request):
        with transaction.atomic():
            # select_for_update: ikki marta tez-tez bosilsa ham bonus faqat 1 marta beriladi
            user = User.objects.select_for_update().get(pk=request.user.pk)
            today, can_claim, day = bonus_state(user)
            if not can_claim:
                return Response({"detail": "Bugungi bonus allaqachon olingan."}, status=400)

            coins, xp = BONUS_REWARDS[day - 1]
            user.coins += coins
            user.xp += xp
            user.bonus_streak = day
            user.last_bonus_date = today
            user.save(update_fields=["coins", "xp", "bonus_streak", "last_bonus_date"])

        return Response(
            {"day": day, "coins_earned": coins, "xp_earned": xp, "user": UserSerializer(user).data}
        )


class AnnouncementListView(APIView):
    def get(self, request):
        items = Announcement.objects.all()[:5]
        return Response(AnnouncementSerializer(items, many=True).data)


# ================= SINXRONIZATSIYA (server.ts ning o'rniga) =================
# Frontend /api/data, /api/rooms ... ga so'rov yuboradi, ma'lumot Neon bazasida saqlanadi.

SYNC_META = "_meta"
SYNC_SECTIONS = [
    "settings", "questions", "schedule", "teachers", "library", "promos",
    "announcements", "homework", "quests", "users", "teacher_accounts",
    "board_rooms",
]
# Bu bo'limlar almashtirilmaydi, birlashtiriladi (akkauntlar yo'qolmasligi uchun)
PROTECTED_SECTIONS = {"users", "teacher_accounts"}

ROOM_MAX_AGE_MS = 6 * 60 * 60 * 1000  # 6 soatdan eski xonalar tozalanadi
BACKUP_SLOTS = 10                      # oxirgi 10 ta zaxira nusxa aylanma saqlanadi


def _now_ms():
    return int(time.time() * 1000)


def _body(request):
    """So'rov tanasi har doim dict bo'lsin (ro'yxat yoki bo'sh kelsa ham xato bermaydi)."""
    data = request.data
    return data if isinstance(data, dict) else {}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _item_key(item):
    if isinstance(item, dict):
        return item.get("id") or item.get("username")
    return None


def _merge_items(old, new, removed=frozenset()):
    """Eski va yangi ro'yxatni birlashtiradi. Hech bir akkaunt o'zi yo'qolmaydi.
    Faqat `removed` da aniq ko'rsatilgan id/username o'chiriladi."""
    merged = {}
    for item in list(old if isinstance(old, list) else []) + list(new if isinstance(new, list) else []):
        k = _item_key(item)
        if k is not None:
            merged[k] = item
    result = []
    for item in merged.values():
        if item.get("id") in removed or item.get("username") in removed:
            continue
        result.append(item)
    return result


def _room_key(room):
    if isinstance(room, dict):
        for f in ("id", "code", "roomId", "roomCode"):
            if room.get(f):
                return str(room[f])
    return None


def _room_time(room):
    for f in ("updatedAt", "lastUpdated", "lastActivity", "updated", "createdAt"):
        n = _num(room.get(f))
        if n is not None:
            return n
    return None


def _merge_rooms(old, new):
    """Xonalarni id/code bo'yicha birlashtiradi: boshqa qurilma yuborgan
    ro'yxat sizning xonangizni o'chirib yubormaydi."""
    merged = {}
    for room in list(old if isinstance(old, list) else []) + list(new if isinstance(new, list) else []):
        k = _room_key(room)
        if k is None:
            continue
        prev = merged.get(k)
        if prev is not None:
            t_old, t_new = _room_time(prev), _room_time(room)
            # yangiroq (yoki vaqti noma'lum bo'lsa, kelgan) versiya yutadi
            if t_old is not None and t_new is not None and t_new < t_old:
                continue
        merged[k] = room

    now = _now_ms()
    result = []
    for room in merged.values():
        t = _room_time(room)
        if t is not None and t > 1e11 and now - t > ROOM_MAX_AGE_MS:
            continue  # eskirgan xona
        result.append(room)
    return result


def _read_db():
    db = {}
    for row in SyncSection.objects.all():
        if row.key == SYNC_META:
            db["version"] = row.data.get("version", 1)
            db["lastUpdated"] = row.data.get("lastUpdated", _now_ms())
        elif row.key.startswith("_"):
            continue  # zaxira nusxalar mijozga ketmaydi
        else:
            db[row.key] = row.data
    db.setdefault("version", 1)
    db.setdefault("lastUpdated", _now_ms())
    return db


def _bump():
    """Versiyani oshiradi. Faqat transaction.atomic() ichida chaqiring.
    Meta qator qulflanadi, shuning uchun bir vaqtdagi yozuvlar navbat bilan bajariladi."""
    for attempt in range(3):
        try:
            with transaction.atomic():
                meta, _ = SyncSection.objects.select_for_update().get_or_create(
                    key=SYNC_META,
                    defaults={"data": {"version": 1, "lastUpdated": _now_ms()}},
                )
                meta.data = {
                    "version": meta.data.get("version", 1) + 1,
                    "lastUpdated": _now_ms(),
                }
                meta.save()
                return meta.data
        except IntegrityError:
            # ikki so'rov bir vaqtda birinchi qatorni yaratmoqchi bo'ldi: qayta urinamiz
            if attempt == 2:
                raise


def _set_section(key, data):
    """Bo'limni saqlaydi (ikki so'rov bir vaqtda yaratsa ham xato bermaydi)."""
    for attempt in range(3):
        try:
            with transaction.atomic():
                SyncSection.objects.update_or_create(key=key, defaults={"data": data})
                return
        except IntegrityError:
            if attempt == 2:
                raise


@api_view(["GET", "HEAD"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def sync_version(request):
    meta = SyncSection.objects.filter(key=SYNC_META).first()
    if meta:
        version = meta.data.get("version", 1)
        last = meta.data.get("lastUpdated", _now_ms())
    else:
        version, last = 1, _now_ms()
    return Response({"version": version, "lastUpdated": last})


@api_view(["GET", "HEAD"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def sync_data(request):
    return Response(_read_db())


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def sync_update(request):
    body = _body(request)
    section = body.get("section")
    if section not in SYNC_SECTIONS:
        return Response({"error": "Invalid section"}, status=400)
    data = body.get("data")
    if data is None:
        return Response({"error": "data kerak"}, status=400)
    removed = {str(x) for x in (body.get("removed") or [])}

    with transaction.atomic():
        # Avval meta qatorni qulflaymiz: bir vaqtdagi yozuvlar bir-birining ustiga yozmaydi
        meta = _bump()

        if section in PROTECTED_SECTIONS:
            if not isinstance(data, list):
                return Response({"error": "List kerak"}, status=400)
            existing = SyncSection.objects.filter(key=section).first()
            old = existing.data if existing else []
            if old:
                # aylanma zaxira nusxa (oxirgi 10 tasi saqlanadi)
                _set_section(f"_backup_{section}_{meta['version'] % BACKUP_SLOTS}", old)
            data = _merge_items(old, data, removed)

        _set_section(section, data)

    result = {"success": True, "section": section, **meta}
    if section in PROTECTED_SECTIONS:
        result["data"] = data  # mijoz birlashgan to'liq ro'yxatni oladi
    return Response(result)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def sync_initial(request):
    payload = _body(request)
    with transaction.atomic():
        _bump_needed = False
        existing = {r.key: r.data for r in SyncSection.objects.all()}
        for s in SYNC_SECTIONS:
            incoming = payload.get(s)
            if not incoming:
                continue
            if s in PROTECTED_SECTIONS and isinstance(incoming, list):
                # brauzerda qolgan akkauntlar ham serverga qo'shiladi, mavjudlari o'chmaydi
                merged = _merge_items(existing.get(s) or [], incoming)
                if merged != (existing.get(s) or []):
                    _set_section(s, merged)
                    _bump_needed = True
            elif not existing.get(s):
                _set_section(s, incoming)
                _bump_needed = True
        if _bump_needed:
            _bump()
    db = _read_db()
    return Response({"success": True, "version": db["version"], "data": db})


@api_view(["GET", "HEAD"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def rooms_get(request):
    row = SyncSection.objects.filter(key="rooms").first()
    rooms = _merge_rooms(row.data if row else [], [])
    return Response({"rooms": rooms})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def rooms_sync(request):
    body = _body(request)
    rooms = body.get("rooms")
    if not isinstance(rooms, list):
        return Response({"error": "Rooms must be array"}, status=400)
    # Ixtiyoriy: frontend o'chirilgan xonalar id/code ro'yxatini yuborsa
    removed = {str(x) for x in (body.get("removed") or [])}

    with transaction.atomic():
        meta = _bump()  # meta qatorni qulflaydi: xonalar bir-birini bosib ketmaydi
        row = SyncSection.objects.filter(key="rooms").first()
        merged = _merge_rooms(row.data if row else [], rooms)
        if removed:
            merged = [r for r in merged if _room_key(r) not in removed]
        _set_section("rooms", merged)
    return Response({"success": True, "count": len(merged), "rooms": merged, **meta})