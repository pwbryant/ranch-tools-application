from django.urls import path
from ranch_tools.preg_check.views import (
    CowCreateView,
    CowCreateUpdateView,
    CowExistsView,
    CowUpdateView,
    PregCheckDetailView,
    PregCheckEditView,
    PregCheckListView,
    PregCheckListBySeasonView,
    PregCheckRecordNewAnimalView,
    PregCheckRollingAverageReport,
    PregCheckSummaryStatsView,
    PreviousPregCheckListView,
    PregCheckReportFive,
    ReportsHubView,
    UpdateCurrentBreedingSeasonView,
)


urlpatterns = [
    path('cows/create/', CowCreateView.as_view(), name='cow-create'),
    path('cows/update/', CowCreateUpdateView.as_view(), name='cow-create-update'),
    path('cows/<int:pk>/update/', CowUpdateView.as_view(), name='cow-update'),
    path('pregchecks/list/<int:breeding_season>', PregCheckListBySeasonView.as_view(), name='pregchecks-by-season'),
    path('pregchecks/reports/', ReportsHubView.as_view(), name='pregcheck-reports'),
    path('pregchecks/', PregCheckListView.as_view(), name='pregcheck-list'),
    path('pregchecks/current-breeding-season/', UpdateCurrentBreedingSeasonView.as_view(), name='pregcheck-breeding-season'),
    path('pregchecks/create/', PregCheckRecordNewAnimalView.as_view(), name='pregcheck-create'),
    path('pregchecks/summary-stats/', PregCheckSummaryStatsView.as_view(), name='pregcheck-summary-stats'),
    path('pregchecks/previous-pregchecks/', PreviousPregCheckListView.as_view(), name='previous-pregchecks'),
    path('pregchecks/<int:pregcheck_id>/edit/', PregCheckEditView.as_view(), name='pregcheck-edit'),
    path('pregchecks/<int:pregcheck_id>/', PregCheckDetailView.as_view(), name='pregcheck-detail'),
    path('pregchecks/report-5/', PregCheckReportFive.as_view(), name='pregcheck-report-5'),
    path('pregchecks/rolling-average-report/', PregCheckRollingAverageReport.as_view(), name='pregcheck-rolling-average-report'),
    path('cow/exists/', CowExistsView.as_view(), name='cow-exists'),
]

