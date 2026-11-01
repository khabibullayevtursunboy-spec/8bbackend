from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """O'quvchi yoki o'qituvchi."""

    class Role(models.TextChoices):
        STUDENT = "student", "O'quvchi"
        TEACHER = "teacher", "O'qituvchi"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    school_class = models.CharField("Sinf", max_length=10, blank=True)  # masalan: 8-B
    coins = models.PositiveIntegerField(default=0)
    xp = models.PositiveIntegerField(default=0)

    # Kunlik bonus (1-7 kun)
    last_bonus_date = models.DateField(null=True, blank=True)
    bonus_streak = models.PositiveSmallIntegerField(default=0)

    @property
    def level(self):
        # Vaqtinchalik formula: har 100 XP = 1 daraja
        return self.xp // 100 + 1

    def __str__(self):
        return self.get_full_name() or self.username


class Question(models.Model):
    """Fan testi savoli (admin panelda A/B/C/D maydonlari orqali qo'shiladi)."""
    subject = models.CharField("Fan", max_length=60)
    text = models.TextField("Savol")
    options = models.JSONField("Variantlar", default=list)
    correct_index = models.PositiveSmallIntegerField("To'g'ri javob raqami (0 dan)")
    explanation = models.TextField("Izoh", blank=True)
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        ordering = ["subject", "id"]
        verbose_name = "Test savoli"
        verbose_name_plural = "Test savollari"

    def __str__(self):
        return f"[{self.subject}] {self.text[:50]}"


class SolvedQuestion(models.Model):
    """Foydalanuvchi to'g'ri yechgan savollar (qayta chiqmaydi)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="solved_questions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="solved_by")
    solved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "question")


class HistoryEvent(models.Model):
    """Tarix Puzzle o'yini uchun voqea (yil + voqea + yordam matni)."""

    class Category(models.TextChoices):
        UZ = "uz", "O'zbekiston tarixi"
        WORLD = "world", "Jahon tarixi"

    year = models.IntegerField("Yil")
    event = models.CharField(
        "Voqea nomi", max_length=160,
        help_text="Kartada ko'rinadi. Masalan: Ankara jangi",
    )
    hint = models.TextField(
        "Yordam matni",
        help_text=(
            "«Yordam» bosilganda tepada «1402-yilda ...» deb chiqadi. "
            "Shuning uchun yilni yozmang, gapni davom ettiring. "
            "Masalan: Amir Temur Usmonli sultoni Boyazid I ni mag'lub etgan."
        ),
    )
    cat = models.CharField("Mavzu", max_length=10, choices=Category.choices, default=Category.UZ)
    is_active = models.BooleanField("Faol", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["year"]
        verbose_name = "Tarix voqeasi"
        verbose_name_plural = "Tarix voqealari"

    def __str__(self):
        return f"{self.year} - {self.event}"


class Announcement(models.Model):
    """Bosh sahifadagi e'lon."""
    title = models.CharField(max_length=120)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Badge(models.Model):
    """Nishon (yutuq) turi."""
    code = models.SlugField(unique=True)
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    icon = models.CharField("Emoji", max_length=8, blank=True)

    def __str__(self):
        return self.title


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "badge")


class GameResult(models.Model):
    """Har bir o'yin natijasi (reyting va tarix uchun)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="results")
    game = models.CharField(max_length=30)  # tests, history_puzzle, memory, millionaire, ...
    score = models.IntegerField(default=0)
    coins_earned = models.PositiveIntegerField(default=0)
    xp_earned = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.game} ({self.score})"


class PromoCode(models.Model):
    code = models.CharField(max_length=40, unique=True)
    coins = models.PositiveIntegerField(default=0)
    xp = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = cheksiz")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Bo'sh = muddatsiz")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class PromoRedemption(models.Model):
    """Kim qaysi kodni ishlatgan (bir kodni bir kishi faqat bir marta)."""
    promo = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="promo_redemptions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("promo", "user")