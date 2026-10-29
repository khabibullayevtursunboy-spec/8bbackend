from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),

    path("auth/register/", views.RegisterView.as_view()),
    path("me/", views.MeView.as_view()),

    path("leaderboard/", views.LeaderboardView.as_view()),

    path("subjects/", views.SubjectListView.as_view()),
    path("questions/", views.QuestionListView.as_view()),
    path("questions/answer/", views.AnswerView.as_view()),

    path("results/", views.ResultView.as_view()),

    path("bonus/", views.BonusStatusView.as_view()),
    path("bonus/claim/", views.BonusClaimView.as_view()),

    path("announcements/", views.AnnouncementListView.as_view()),
]