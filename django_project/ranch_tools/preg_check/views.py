from datetime import datetime, timezone
import json
from urllib.parse import urlencode

from django.db.models import F, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, FormView
from django.views.generic.edit import UpdateView

from ranch_tools.preg_check.forms import (
    AnimalSearchForm,
    CowForm,
    EditPregCheckForm,
    PregCheckForm
)
from ranch_tools.preg_check.models import Cow, CurrentBreedingSeason, PregCheck
from ranch_tools.utils.mixins import InitialzeDatabaseMixin


from pdb import set_trace as bp



def get_matching_cows(ear_tag_id=None, rfid=None, birth_year=None):
    '''
    Return cows that are associated with ear_tag_id and birth_year, if present, OR
    rfid value.  If both ear_tag_id and rfid are provided, assert that the ids belong
    to the same cow.
    '''
    # Build the query using Q objects
    query = Q()
    if ear_tag_id and birth_year:
        query |= Q(ear_tag_id=ear_tag_id, birth_year=birth_year)
    elif ear_tag_id:
        query |= Q(ear_tag_id=ear_tag_id)

    if rfid:
        query |= Q(eid=rfid)  # Assuming 'eid' is the field for RFID in the Cow model


    if not query:
        return Cow.objects.none()

    matching_cows = Cow.objects.filter(query)
    if matching_cows.filter(eid=rfid) and matching_cows.filter(ear_tag_id=ear_tag_id):
        cow = matching_cows.get(eid=rfid)
        if cow.ear_tag_id != ear_tag_id:
            raise Exception("Conflicting rfid and ear tag.  Make sure each id is correct.")
        
    return matching_cows


def get_pregchecks_from_cows(cows):
    # Build the query using Q objects

    if not cows.exists():
        return PregCheck.objects.none()
    query = Q()
    for cow in cows:
        query |= Q(cow=cow)
    pregchecks = PregCheck.objects.filter(query)
    return pregchecks


class PreviousPregCheckListView(View):
    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get('limit', 5))
        current_breeding_season = CurrentBreedingSeason.load().breeding_season
        pregchecks = PregCheck.objects.filter(
            breeding_season=current_breeding_season
        ).annotate(
            ear_tag_id=F('cow__ear_tag_id'), animal_birth_year=F('cow__birth_year')
        ).order_by('-check_date' , '-id')
        pregchecks = pregchecks.values()[:limit]
        return JsonResponse({'pregchecks': list(pregchecks)}, safe=False)


class PregCheckListView(ListView, InitialzeDatabaseMixin):
    model = PregCheck
    template_name = 'pregcheck_list.html'
    context_object_name = 'pregchecks'

    def dispatch(self, request, *args, **kwargs):
        self.initialze_database_if_needed()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        ear_tag_id = self.request.GET.get('search_ear_tag_id', '')
        rfid = self.request.GET.get('search_rfid', '')
        birth_year = self.request.GET.get('search_birth_year', None)
        if 'all' in (ear_tag_id.strip().lower(), rfid.strip().lower()):
            current_breeding_season = CurrentBreedingSeason.load().breeding_season
            queryset = PregCheck.objects.filter(
                breeding_season=current_breeding_season
            ).order_by('-check_date' , '-id')
        elif ear_tag_id or rfid:
            queryset = get_pregchecks_from_cows(get_matching_cows(ear_tag_id=ear_tag_id, rfid=rfid))
            if birth_year:
                queryset = queryset.filter(cow__birth_year=birth_year)
            queryset = queryset.order_by('-check_date', '-id')
        else:
            queryset = PregCheck.objects.none()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pregcheck_form = PregCheckForm()
        birth_year = self.request.GET.get('search_birth_year', None)
        if birth_year:
            pregcheck_form.fields['birth_year'].initial = birth_year

        ear_tag_id = self.request.GET.get('search_ear_tag_id', '')
        rfid = self.request.GET.get('search_rfid', '')
        animals = get_matching_cows(ear_tag_id=ear_tag_id, rfid=rfid, birth_year=birth_year)
        animal_exists = animals.exists()        

        animal_count = animals.count()
        cow = None
        if animal_count == 1:
            cow = animals[0]
            distinct_birth_years = [cow.birth_year]
            birth_year = cow.birth_year
        elif animal_count > 1:
            distinct_birth_years = animals.values_list('birth_year', flat=True).distinct()
        else:
            distinct_birth_years = []

        if cow:
            pregcheck_form.fields['pregcheck_ear_tag_id'].initial = cow.ear_tag_id
            pregcheck_form.fields['pregcheck_rfid'].initial = cow.eid
            pregcheck_form.fields['birth_year'].initial = cow.birth_year
            last_pregcheck = PregCheck.objects.last()
            last_pregcheck_created_date = last_pregcheck.created_on.date()
            if last_pregcheck_created_date == datetime.today().astimezone(timezone.utc).date():
                pregcheck_form.fields['check_date'].initial = last_pregcheck.check_date

        search_form = AnimalSearchForm(
            initial={'search_ear_tag_id': ear_tag_id,
                     'search_rfid': rfid,
                     'search_birth_year': birth_year
            },
            birth_year_choices=[(y, str(y),) for y in distinct_birth_years]
        )
        current_breeding_season = CurrentBreedingSeason.load().breeding_season
        pregcheck_form.fields['breeding_season'].initial = current_breeding_season

        if animal_count == 1:
            preg_checks_this_season = PregCheck.objects.filter(
                cow=cow, breeding_season=current_breeding_season
            ).count()
            pregcheck_form.fields['recheck'].initial = preg_checks_this_season > 0

        context['current_breeding_season'] = current_breeding_season
        context['all_preg_checks'] = ear_tag_id.strip().lower() == 'all'
        latest_breeding_season = None
        if PregCheck.objects.exists():
            latest_breeding_season = PregCheck.objects.latest('id').breeding_season
        else:
            latest_breeding_season = current_breeding_season
        context['latest_breeding_season'] = latest_breeding_season
        context['search_form'] = search_form
        context['pregcheck_form'] = pregcheck_form
        context['animal_exists'] = animal_exists
        context['multiple_matches'] = animal_count > 1
        context['distinct_birth_years'] = distinct_birth_years
        context['cow'] = cow
        return context


class PregCheckListBySeasonView(ListView):
    model = PregCheck
    template_name = 'preg_check/pregcheck_by_season_list.html'
    context_object_name = 'pregchecks'

    def get_queryset(self):
        qs = super().get_queryset()
        breeding_season = self.kwargs.get('breeding_season')
        return qs.filter(breeding_season=breeding_season)


class UpdateCurrentBreedingSeasonView(View):

    def post(self, request, *args, **kwargs):
        try:
            # Assuming you're sending data as JSON
            data = json.loads(request.body)
            breeding_season = int(data.get('breeding_season'))
            current_season = CurrentBreedingSeason.load()
            current_season.breeding_season = breeding_season
            current_season.save()
            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})


class PregCheckRecordNewAnimalView(CreateView):
    model = PregCheck
    form_class = PregCheckForm

    def get(self, request, *args, **kwargs):
       # This view only handles POST requests, so for GET requests,
       # simply redirect to PregCheckListView.
        return HttpResponseRedirect(reverse('pregcheck-list'))

    def get_initial(self):
        initial = super().get_initial()
        ear_tag_id = self.kwargs.get('ear_tag_id')
        if ear_tag_id:
            initial['pregcheck_ear_tag_id'] = ear_tag_id

        return initial

    def form_valid(self, form):
        ear_tag_id = form.cleaned_data['pregcheck_ear_tag_id']
        ear_tag_id = None if not ear_tag_id else ear_tag_id
        rfid = form.cleaned_data['pregcheck_rfid']
        rfid = None if not rfid else rfid
        birth_year = form.cleaned_data['birth_year']
        birth_year = None if not birth_year else birth_year
        cow_params = {}
        if ear_tag_id:
            cow_params['ear_tag_id'] = ear_tag_id
        if rfid:
            cow_params['eid'] = rfid
        if birth_year:
            cow_params['birth_year'] = birth_year

        if cow_params:
            cow = Cow.objects.get(**cow_params)
            form.instance.cow = cow

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('pregcheck-list')

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class PregCheckSummaryStatsView(View):
    def get(self, request, *args, **kwargs):
        stats_breeding_season = request.GET.get('stats_breeding_season')

        if not stats_breeding_season:
            return HttpResponseBadRequest("stats_breeding_season parameter is required.")

        all_checks = PregCheck.objects.filter(breeding_season=stats_breeding_season)
        total_pregnant_count = all_checks.filter(is_pregnant=True).count()
        all_opens_count = all_checks.filter(is_pregnant=False).count()

        rechecks = all_checks.filter(recheck=True)
        preg_rechecks_count = rechecks.filter(is_pregnant=True).count()
        open_rechecks_count = rechecks.filter(is_pregnant=False).count()

        first_pass_pregs_count = total_pregnant_count - preg_rechecks_count
        first_pass_open_count = all_opens_count - open_rechecks_count

        total_open_count = first_pass_open_count - preg_rechecks_count
        total_count = total_open_count + total_pregnant_count
        pregnancy_rate = (total_pregnant_count / total_count) * 100 if total_count > 0 else 0

        summary_stats = {
            'first_check_pregnant': first_pass_pregs_count,
            'recheck_pregnant': preg_rechecks_count,
            'total_pregnant': total_pregnant_count,
            'first_check_open': first_pass_open_count,
            'less_recheck_pregnant': preg_rechecks_count,
            'total_open': total_open_count,
            'total_count': total_count,
            'pregnancy_rate': pregnancy_rate
	}

        return JsonResponse(summary_stats)


class CowCreateUpdateView(FormView):
    form_class = CowForm
    template_name = 'preg_check/includes/no_animal_modal.html'
    # success_url = reverse('pregcheck-list')

    def get_success_url(self):
        cow = self.object
        query_parameters = {
            'search_ear_tag_id': cow.ear_tag_id,
            'search_birth_year': cow.birth_year,
            'search_rfid': cow.eid
        }
        return reverse('pregcheck-list') + '?' + urlencode(query_parameters)

    def get_object(self):
        ear_tag_id = self.request.POST.get('ear_tag_id')
        rfid = self.request.POST.get('rfid')
        birth_year = self.request.POST.get('birth_year')
        
        cows = Cow.objects.none()
        if ear_tag_id:
            cows = Cow.objects.filter(ear_tag_id=ear_tag_id)
            if cows.count() > 1 and birth_year:
                cows = cows.filter(birth_year=birth_year)
        if rfid:
            cows = Cow.objects.filter(eid=rfid)

        cow_count = cows.count()
        if cow_count > 1:
            raise Exception('There is more than one cow associated with this information.')
        elif cow_count == 1:
            return cows[0]
        else:
            return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        cow = self.get_object()
        if cow:
            kwargs['instance'] = cow
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cow = self.get_object()
        context['is_update'] = cow is not None
        context['object'] = cow
        return context

    def form_valid(self, form):
        self.object = form.save()
        is_valid = super().form_valid(form)
        return super().form_valid(form)
    
    def form_invalid(self, form):
        raise Exception(f'Form is invalid: {form.errors}')


class CowCreateView(CreateView):
    model = Cow
    form_class = CowForm

    def get_success_url(self):
        cow = self.object
        query_parameters = {
            'search_ear_tag_id': cow.ear_tag_id,
            'search_birth_year': cow.birth_year,
            'search_rfid': cow.eid
        }
        url = reverse('pregcheck-list') + '?' + urlencode(query_parameters)
        return url


class CowUpdateView(UpdateView):
    model = Cow
    fields = ['birth_year', 'eid']
    template_name = 'path_to_template.html'  # Replace with the path to your template for updating the cow
    
    def form_valid(self, form):
        # Save the updated cow instance
        self.object = form.save()

        # Construct the URL for redirection
        redirect_url = reverse('pregcheck-list')
        query_parameters = {
            'search_ear_tag_id': self.object.ear_tag_id,
            'search_birth_year': form.cleaned_data['birth_year'],
            'search_rfid': self.object.eid
        }
        full_redirect_url = redirect_url + '?' + urlencode(query_parameters)
        
        return redirect(full_redirect_url)
    
    def get_success_url(self):
        # This method might not be called due to our custom redirection in form_valid method, but just in case:
        return reverse('pregcheck-list')


class CowExistsView(View):
    def get(self, request):
        ear_tag_id = request.GET.get('ear_tag_id')
        if ear_tag_id:
            cows =  Cow.objects.filter(ear_tag_id=ear_tag_id)
            cow_exists = cows.exists()
            if cows.count() > 1:
                data = {'exists' : cow_exists, 'multiple_matches': True}    
            else:
                data = {'exists': cow_exists}

            return JsonResponse(data)
        else:
            return JsonResponse({'error': 'check_existing_ear_tag_id parameter is required'}, status=400)


class PregCheckEditView(View):
    def post(self, request, pregcheck_id):
        try:
            pregcheck = PregCheck.objects.get(pk=pregcheck_id)
        except PregCheck.DoesNotExist:
            return JsonResponse({'error': 'PregCheck not found'}, status=404)

        form = EditPregCheckForm(request.POST, instance=pregcheck)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': 'PregCheck updated successfully'})
        else:
            errors = form.errors.as_json()
            return JsonResponse({'errors': errors}, status=400)


class PregCheckDetailView(View):

    def get(self, request, pregcheck_id):
        # Retrieve the PregCheck object or return a 404 response if not found
        pregcheck = get_object_or_404(PregCheck, pk=pregcheck_id)
        
        pregcheck_details = {
            'id': pregcheck.id,
            'is_pregnant': pregcheck.is_pregnant,
            'comments': pregcheck.comments,
            'recheck': pregcheck.recheck,
        }

        return JsonResponse(pregcheck_details)

