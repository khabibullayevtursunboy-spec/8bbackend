from datetime import timedelta

from django.db import transaction
from django.db.models import F, Sum, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    User, Question, SolvedQuestion, HistoryEvent, Announcement,
    GameResult, PromoCode, PromoRedemption,
)
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

@api_view(["GET"])
@permission_classes([AllowAny])
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

        limits = GAME_LIMITS[data["game"]]
        coins = min(data["coins_earned"], limits["coins"])
        xp = min(data["xp_earned"], limits["xp"])

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
            # select_for_update: tez-tez bosilsa ham bonus faqat 1 marta beriladi
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


class PromoThrottle(UserRateThrottle):
    scope = "promo"  # kodlarni taxmin qilib topishdan himoya


class RedeemPromoView(APIView):
    throttle_classes = [PromoThrottle]

    def post(self, request):
        code = str(request.data.get("code", "")).strip().upper()
        if not code:
            return Response({"detail": "Promokodni kiriting."}, status=400)

        with transaction.atomic():
            promo = (
                PromoCode.objects.select_for_update()
                .filter(code=code, is_active=True)
                .first()
            )
            if not promo:
                return Response({"detail": "Bunday promokod mavjud emas."}, status=400)
            if promo.expires_at and promo.expires_at < timezone.now():
                return Response({"detail": "Promokod muddati tugagan."}, status=400)
            if PromoRedemption.objects.filter(promo=promo, user=request.user).exists():
                return Response({"detail": "Siz bu promokodni allaqachon ishlatgansiz."}, status=400)
            if promo.max_uses and promo.redemptions.count() >= promo.max_uses:
                return Response({"detail": "Promokod limiti tugagan."}, status=400)

            PromoRedemption.objects.create(promo=promo, user=request.user)
            apply_reward(request.user, promo.coins, promo.xp)

        return Response(
            {"coins_earned": promo.coins, "xp_earned": promo.xp, "user": UserSerializer(request.user).data}
        )


# ================= O'YIN KONTENTI (hamma uchun ochiq, login kerak emas) =================

class HistoryContentView(APIView):
    """Tarix Puzzle voqealari. Admin panelda qo'shilgan voqealar shu yerdan olinadi."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        rows = HistoryEvent.objects.filter(is_active=True).values(
            "id", "year", "event", "hint", "cat"
        )
        return Response(list(rows))