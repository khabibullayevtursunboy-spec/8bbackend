from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, Question, Announcement, Badge, UserBadge, GameResult


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


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("subject", "text", "correct_index", "is_active")
    list_filter = ("subject", "is_active")
    search_fields = ("text",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "created_at")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("icon", "title", "code")


admin.site.register(UserBadge)


@admin.register(GameResult)
class GameResultAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "score", "coins_earned", "xp_earned", "created_at")
    list_filter = ("game",)