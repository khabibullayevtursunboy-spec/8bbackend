from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    User, Question, SolvedQuestion, HistoryEvent, Announcement, Badge,
    UserBadge, GameResult, PromoCode, PromoRedemption,
)

admin.site.site_header = "8-sinf Gaming Portal"
admin.site.site_title = "8-sinf Admin"
admin.site.index_title = "Boshqaruv paneli"


# ===================== Foydalanuvchilar =====================

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("O'yin ma'lumotlari", {
            "fields": ("role", "school_class", "coins", "xp", "last_bonus_date", "bonus_streak")
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {"fields": ("role", "school_class")}),
    )
    list_display = ("username", "first_name", "last_name", "school_class", "role", "coins", "xp")
    list_filter = ("role", "school_class")
    search_fields = ("username", "first_name", "last_name")


# ===================== Test savollari (oson forma) =====================

OPTION_FIELDS = ("option_a", "option_b", "option_c", "option_d")
LETTERS = "ABCD"


class QuestionAdminForm(forms.ModelForm):
    """Variantlarni JSON o'rniga A/B/C/D maydonlariga yozish uchun."""
    option_a = forms.CharField(label="A variant", max_length=200)
    option_b = forms.CharField(label="B variant", max_length=200)
    option_c = forms.CharField(label="C variant", max_length=200, required=False)
    option_d = forms.CharField(label="D variant", max_length=200, required=False)
    correct = forms.ChoiceField(label="To'g'ri javob", choices=[(l, l) for l in LETTERS])

    class Meta:
        model = Question
        fields = ("subject", "text", "explanation", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        q = self.instance
        if q and q.pk:
            opts = list(q.options or [])
            for i, name in enumerate(OPTION_FIELDS):
                self.fields[name].initial = opts[i] if i < len(opts) else ""
            if 0 <= q.correct_index < len(LETTERS):
                self.fields["correct"].initial = LETTERS[q.correct_index]

    def clean(self):
        cleaned = super().clean()
        correct = cleaned.get("correct")
        if correct is None:
            return cleaned

        raw = [(cleaned.get(name) or "").strip() for name in OPTION_FIELDS]
        pos = LETTERS.index(correct)
        if not raw[pos]:
            raise forms.ValidationError(
                f"To'g'ri javob sifatida {correct} tanlangan, lekin {correct} varianti bo'sh."
            )
        options = [o for o in raw if o]
        if len(options) < 2:
            raise forms.ValidationError("Kamida 2 ta variant kiriting.")

        self._options = options
        self._correct_index = sum(1 for o in raw[:pos] if o)
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.options = self._options
        obj.correct_index = self._correct_index
        if commit:
            obj.save()
        return obj


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionAdminForm
    fields = (
        "subject", "text",
        "option_a", "option_b", "option_c", "option_d", "correct",
        "explanation", "is_active",
    )
    list_display = ("subject", "short_text", "correct_letter", "is_active")
    list_filter = ("subject", "is_active")
    search_fields = ("text", "subject")
    save_as = True  # "Saqlash va yangi sifatida qo'shish": o'xshash savolni tez qo'shish uchun

    @admin.display(description="Savol")
    def short_text(self, obj):
        return obj.text[:70]

    @admin.display(description="To'g'ri")
    def correct_letter(self, obj):
        return LETTERS[obj.correct_index] if 0 <= obj.correct_index < len(LETTERS) else "?"


# ===================== Tarix Puzzle =====================

@admin.register(HistoryEvent)
class HistoryEventAdmin(admin.ModelAdmin):
    list_display = ("year", "event", "cat", "is_active")
    list_filter = ("cat", "is_active")
    list_editable = ("is_active",)
    search_fields = ("event", "hint")
    ordering = ("year",)
    save_as = True


# ===================== Boshqalar =====================

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "created_at")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("icon", "title", "code")


@admin.register(GameResult)
class GameResultAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "score", "coins_earned", "xp_earned", "created_at")
    list_filter = ("game",)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "coins", "xp", "max_uses", "expires_at", "is_active")
    list_filter = ("is_active",)


admin.site.register(UserBadge)
admin.site.register(SolvedQuestion)
admin.site.register(PromoRedemption)