from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

urlpatterns = [
    path("health/", views.health),

    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", TokenObtainPairView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("me/", views.MeView.as_view()),

    path("leaderboard/", views.LeaderboardView.as_view()),

    path("subjects/", views.SubjectListView.as_view()),
    path("questions/", views.QuestionListView.as_view()),
    path("questions/answer/", views.AnswerView.as_view()),

    path("results/", views.ResultView.as_view()),

    path("bonus/", views.BonusStatusView.as_view()),
    path("bonus/claim/", views.BonusClaimView.as_view()),

    path("announcements/", views.AnnouncementListView.as_view()),

    # Sinxronizatsiya (server.ts o'rniga)
    path("version", views.sync_version),
    path("data", views.sync_data),
    path("data/update", views.sync_update),
    path("data/sync", views.sync_initial),
    path("rooms", views.rooms_get),
    path("rooms/sync", views.rooms_sync),
]