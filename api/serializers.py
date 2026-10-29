from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User, Question, Announcement

# Qaysi o'yinlar natija yubora oladi (views.py dagi GAME_LIMITS bilan bir xil bo'lishi kerak)
GAME_CHOICES = [
    "history_puzzle", "memory", "millionaire",
    "tugofwar", "multiplayer", "boardgames", "pomodoro",
]


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    level = serializers.IntegerField(read_only=True)
    badges = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "first_name", "last_name", "full_name",
            "school_class", "role", "coins", "xp", "level",
            "bonus_streak", "badges",
        )
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_badges(self, obj):
        return [
            {"code": ub.badge.code, "title": ub.badge.title, "icon": ub.badge.icon}
            for ub in obj.badges.select_related("badge")
        ]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("username", "password", "first_name", "last_name", "school_class")
        extra_kwargs = {
            "first_name": {"required": True},
            "last_name": {"required": True},
            "school_class": {"required": True},
        }

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        # MUHIM: role har doim "student". Mijozdan role qabul qilinmaydi,
        # o'qituvchi akkauntini faqat admin panelda yaratasiz.
        return User.objects.create_user(role=User.Role.STUDENT, **validated_data)


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "school_class")


class QuestionPublicSerializer(serializers.ModelSerializer):
    """To'g'ri javob va izoh YUBORILMAYDI (aldashning oldini olish uchun)."""

    class Meta:
        model = Question
        fields = ("id", "subject", "text", "options")


class AnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_index = serializers.IntegerField(min_value=0)


class ResultSerializer(serializers.Serializer):
    game = serializers.ChoiceField(choices=GAME_CHOICES)
    score = serializers.IntegerField(min_value=0, max_value=1_000_000)
    coins_earned = serializers.IntegerField(min_value=0, max_value=100_000)
    xp_earned = serializers.IntegerField(min_value=0, max_value=100_000)


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ("id", "title", "content", "created_at")