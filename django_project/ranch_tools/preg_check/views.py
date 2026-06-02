from datetime import datetime, timezone
import json
from urllib.parse import urlencode

from django.db import models
from django.db.models import F, Q, Max
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
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
        rfid = self.request.GET.get('search_rfid')
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
            if last_pregcheck:
                last_pregcheck_created_date = last_pregcheck.created_on.date()
                if last_pregcheck_created_date == datetime.today().astimezone(timezone.utc).date():
                    pregcheck_form.fields['check_date'].initial = last_pregcheck.check_date
            
            last_cow_pregcheck = PregCheck.objects.filter(cow=cow).order_by('check_date', 'id').last()
            if last_cow_pregcheck:
                pregcheck_form.fields['should_sell'].initial = last_cow_pregcheck.should_sell

        search_form = AnimalSearchForm(
            initial={'search_ear_tag_id': ear_tag_id,
                     'search_rfid': '' if rfid is None else rfid,
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

        # with cow checks
        checks_with_cows = PregCheck.latest_objects.filter(breeding_season=stats_breeding_season).latest_per_cow()

        total_pregnant_count = checks_with_cows.filter(is_pregnant=True).count()
        total_opens_count = checks_with_cows.filter(is_pregnant=False).count()
        total_count = total_pregnant_count + total_opens_count

        pregnancy_rate = (total_pregnant_count / total_count) * 100 if total_count > 0 else 0

        checks_without_cows = PregCheck.objects.filter(cow=None, breeding_season=stats_breeding_season)
        total_no_cow_pregnant_count = checks_without_cows.filter(is_pregnant=True).count()
        total_no_cow_opens_count = checks_without_cows.filter(is_pregnant=False).count()
        total_no_cow_count = total_no_cow_pregnant_count + total_no_cow_opens_count

        no_cow_pregnancy_rate = (total_no_cow_pregnant_count / total_no_cow_count) * 100 if total_no_cow_count > 0 else 0

        summary_stats = {
            # 'first_check_pregnant': first_pass_pregs_count,
            # 'recheck_pregnant': preg_rechecks_count,
            'total_pregnant': total_pregnant_count,
            # 'first_check_open': first_pass_open_count,
            # 'less_recheck_pregnant': preg_rechecks_count,
            'total_open': total_opens_count,
            'total_count': total_count,
            'pregnancy_rate': pregnancy_rate,

            'total_no_cow_pregnant_count': total_no_cow_pregnant_count,
            'total_no_cow_opens_count': total_no_cow_opens_count,
            'total_no_cow_count': total_no_cow_count,
            'no_cow_pregnancy_rate': no_cow_pregnancy_rate,
    	}

        return JsonResponse(summary_stats)


class CowCreateUpdateView(FormView):
    form_class = CowForm
    template_name = 'preg_check/includes/no_animal_modal.html'

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
    fields = ['birth_year', 'eid', 'ear_tag_id']
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


def pregcheck_info_by_cow(pgs) -> dict:
    d = {}
    for pg in pgs.order_by('-check_date'):
        key = f'{pg.cow.ear_tag_id}-{pg.cow.birth_year}'
        if key not in d:
            d[key] = {
                'latest_pregcheck': pg,
                'previous_pregchecks': []
            }
        else:
            d[key]['previous_pregchecks'].append(pg)

    return d


class PregCheckReportFive(View):
    """Simple view to render Report Five page"""

    def get(self, request, *args, **kwargs):
        # Allow overriding breeding season via query param
        season = request.GET.get('breeding_season')
        if season:
            try:
                breeding_season = int(season)
            except ValueError:
                breeding_season = CurrentBreedingSeason.load().breeding_season
        else:
            breeding_season = CurrentBreedingSeason.load().breeding_season

        all_breeding_season_cows = PregCheck.objects.filter(breeding_season=breeding_season)

        if all_breeding_season_cows.count() == 0:
            context = {
                'breeding_season': breeding_season,
                'rows': [],
                'totals': {},
            }
            return render(request, 'preg_check/report-5.html', context)

        all_pregchecks_with_NO_cow = all_breeding_season_cows.filter(cow=None)

        all_pregchecks_with_cow = all_breeding_season_cows.exclude(id__in=all_pregchecks_with_NO_cow)
        all_pregchecks_with_cow = all_pregchecks_with_cow.annotate(cow_age=breeding_season-models.F('cow__birth_year'))

        all_pregchecks_with_cow_initial = all_pregchecks_with_cow.filter(recheck=False)
        all_pregchecks_with_cow_recheck = all_pregchecks_with_cow.filter(recheck=True)

        cow_ages = sorted(all_pregchecks_with_cow.values_list('cow_age', flat=True).distinct())
        cow_ages
        rows = []
        for age in cow_ages:
            birth_year = breeding_season - age
            age_pregchecks = all_pregchecks_with_cow.filter(cow_age=age)
            row = self.create_preg_checks_row(age_pregchecks, age=age, birth_year=birth_year)
            if row:
                rows.append(row)


        no_cow_row = self.create_no_cow_preg_check_row(all_pregchecks_with_NO_cow)

        totals_row = self.create_preg_checks_row(all_pregchecks_with_cow)

        totals_row['cow_birth_year'] = 'TOTALS'
        totals_row['is_totals'] = True
        context = {
            'breeding_season': breeding_season,
            'rows': rows,
            'totals': totals_row,
            'no_cow_row': no_cow_row
        }

        return render(request, 'preg_check/report-5.html', context)

    def create_no_cow_preg_check_row(self, no_cow_preg_checks):
        open_count = no_cow_preg_checks.filter(is_pregnant=False).count()
        pregnant_count = no_cow_preg_checks.filter(is_pregnant=True).count()
        herd_size = open_count + pregnant_count
        if herd_size == 0:
            pct_pregnant = 0
        else:
            pct_pregnant = pregnant_count / herd_size * 100 
        return {
            'net_open': open_count, 
            'net_pregnant': pregnant_count,
            'pct_pregnant': f"{pct_pregnant:.1f}%",
        }

    def create_preg_checks_row(self, preg_checks, age=None, birth_year=None):

        cow_pregcheck_info_dict = pregcheck_info_by_cow(preg_checks)

        first_pass_open_count = 0
        first_pass_pregnant_count = 0
        for cow_id in cow_pregcheck_info_dict:
            cow_dict = cow_pregcheck_info_dict[cow_id]
            if cow_dict['previous_pregchecks']:
                first_cow = cow_dict['previous_pregchecks'][-1]  # sorted by reverse check_date
            else:
                first_cow = cow_dict['latest_pregcheck']

            if first_cow.is_pregnant:
                first_pass_pregnant_count += 1
            else:
                first_pass_open_count += 1

        preg_recheck_count = first_pass_pregnant_count
        open_recheck_count = first_pass_open_count
        for cow_id in cow_pregcheck_info_dict:
            cow_dict = cow_pregcheck_info_dict[cow_id]
            if cow_dict['previous_pregchecks']:
                latest_pregcheck = cow_dict['latest_pregcheck']
                previous_pregcheck = cow_dict['previous_pregchecks'][0]

                latest_cow_pregnant = latest_pregcheck.is_pregnant is True
                latest_cow_open = latest_pregcheck.is_pregnant is False
                previous_cow_pregnant = previous_pregcheck.is_pregnant is True
                previous_cow_open = previous_pregcheck.is_pregnant is False

                # if previous cow is open and latest cow is open then it is assumed
                # it is an unecessary recheck and nothing new is counted

                # if previous is open but latest is pregnant then update counts
                if previous_cow_open and latest_cow_pregnant:
                    open_recheck_count -= 1
                    preg_recheck_count += 1

                # if previous preg but latest is open, then assume a mistake was made on the initial
                # check and update the first pass counts
                if previous_cow_pregnant and latest_cow_open:
                    first_pass_open_count += 1
                    first_pass_pregnant_count -= 1

                    open_recheck_count += 1
                    preg_recheck_count -= 1

        first_pass_total = first_pass_open_count + first_pass_pregnant_count
        recheck_total = open_recheck_count + preg_recheck_count

        herd_size = len(cow_pregcheck_info_dict) # key for each unique cow
        
        pct_pregnant = preg_recheck_count / herd_size * 100

        return {
            'cow_birth_year': birth_year,
            'age': age,
            'first_pass_open': first_pass_open_count,
            'first_pass_pregnant': first_pass_pregnant_count,
            'first_pass_total': first_pass_total,
            'recheck_open': open_recheck_count,
            'recheck_pregnant': preg_recheck_count, # if recheck, the recheck cow is used
            'recheck_total': recheck_total,
            'pct_pregnant': f"{pct_pregnant:.1f}%",
        }

    def xxxget(self, request, *args, **kwargs):
        # Allow overriding breeding season via query param
        season = request.GET.get('breeding_season')
        if season:
            try:
                breeding_season = int(season)
            except ValueError:
                breeding_season = CurrentBreedingSeason.load().breeding_season
        else:
            breeding_season = CurrentBreedingSeason.load().breeding_season



        # All pregchecks for the season (used for counting unique cows and preg status)
        all_pregchecks = PregCheck.objects.filter(breeding_season=breeding_season).select_related('cow').order_by('cow_id', 'check_date', 'created_on')

        # Build sets per birth_year (or 'Unknown'):
        # total_cows_by_birth_year: set of unique cow keys (or pseudo-ids for unknown checks)
        # pregnant_cows_by_birth_year: set of unique cow keys that had any pregnant record
        total_cows_by_birth_year = {}
        pregnant_cows_by_birth_year = {}
        for pc in all_pregchecks:
            if pc.cow and pc.cow.birth_year is not None:
                by_key = pc.cow.birth_year
                cow_key = f"cow-{pc.cow.id}"
            else:
                by_key = 'Unknown'
                cow_key = f"unknown-{pc.id}"

            total_cows_by_birth_year.setdefault(by_key, set()).add(cow_key)
            if pc.is_pregnant:
                pregnant_cows_by_birth_year.setdefault(by_key, set()).add(cow_key)

        # We want only the first PregCheck per cow for the season (first-pass)
        first_check_by_cow = {}
        for pc in all_pregchecks:
            if pc.cow and pc.cow.birth_year is not None:
                cow_key = f"cow-{pc.cow.id}"
            else:
                cow_key = f"unknown-{pc.id}"
            if cow_key not in first_check_by_cow:
                first_check_by_cow[cow_key] = pc

        # Aggregate first-pass counts by birth_year (including 'Unknown')
        stats_by_birth_year = {}
        for pc in first_check_by_cow.values():
            if pc.cow and pc.cow.birth_year is not None:
                by = pc.cow.birth_year
            else:
                by = 'Unknown'
            entry = stats_by_birth_year.setdefault(by, {'first_pass_open': 0, 'first_pass_pregnant': 0})
            if pc.is_pregnant:
                entry['first_pass_pregnant'] += 1
            else:
                entry['first_pass_open'] += 1

        # Count unique cows that had at least one recheck=True in the season, grouped by birth_year
        preg_rechecks = PregCheck.objects.filter(breeding_season=breeding_season, recheck=True).select_related('cow')
        preg_recheck_counts = {}
        preg_recheck_cows_by_by = {}
        for pc in preg_rechecks:
            if pc.cow and pc.cow.birth_year is not None:
                by = pc.cow.birth_year
                cow_key = f"cow-{pc.cow.id}"
            else:
                by = 'Unknown'
                cow_key = f"unknown-{pc.id}"
            preg_recheck_cows_by_by.setdefault(by, set()).add(cow_key)
        for by, cow_set in preg_recheck_cows_by_by.items():
            preg_recheck_counts[by] = len(cow_set)

        # Convert to a sorted list of rows and compute derived columns
        rows = []
        # Sort numeric birth years descending, then Unknown last
        numeric_keys = sorted([k for k in stats_by_birth_year.keys() if k != 'Unknown'], reverse=True)
        ordered_keys = numeric_keys + (['Unknown'] if 'Unknown' in stats_by_birth_year else [])
        for by in ordered_keys:
            counts = stats_by_birth_year[by]
            age = breeding_season - by if by != 'Unknown' else None
            first_pass_open = counts.get('first_pass_open', 0)
            first_pass_pregnant = counts.get('first_pass_pregnant', 0)
            preg_recheck_count = preg_recheck_counts.get(by, 0)
            first_pass_total = first_pass_open + first_pass_pregnant
            net_open = first_pass_open - preg_recheck_count
            net_pregnant = first_pass_pregnant + preg_recheck_count

            # pct_pregnant: percent of cows (unique) that were pregnant at any time in the season
            total_cows = len(total_cows_by_birth_year.get(by, set()))
            pregnant_cows = len(pregnant_cows_by_birth_year.get(by, set()))
            pct = (pregnant_cows / total_cows * 100) if total_cows > 0 else 0

            display_by = 'Unknown Cow' if by == 'Unknown' else by

            rows.append({
                'cow_birth_year': display_by,
                'age': age,
                'first_pass_open': first_pass_open,
                'first_pass_pregnant': first_pass_pregnant,
                'first_pass_total': first_pass_total,
                'preg_recheck_count': preg_recheck_count,
                'net_open': net_open,
                'net_pregnant': net_pregnant,
                'pct_pregnant': f"{pct:.1f}%",
            })

        # Calculate totals row
        if rows:
            total_first_pass_open = sum(int(r['first_pass_open']) for r in rows)
            total_first_pass_pregnant = sum(int(r['first_pass_pregnant']) for r in rows)
            total_first_pass_total = sum(int(r['first_pass_total']) for r in rows)
            total_preg_recheck_count = sum(int(r['preg_recheck_count']) for r in rows)
            total_net_open = sum(int(r['net_open']) for r in rows)
            total_net_pregnant = sum(int(r['net_pregnant']) for r in rows)
            
            # Calculate average pct_pregnant
            pct_values = []
            for r in rows:
                # Extract numeric value from percentage string
                pct_str = r['pct_pregnant'].replace('%', '')
                pct_values.append(float(pct_str))
            avg_pct = sum(pct_values) / len(pct_values) if pct_values else 0
            
            totals_row = {
                'cow_birth_year': 'TOTALS',
                'age': None,
                'first_pass_open': total_first_pass_open,
                'first_pass_pregnant': total_first_pass_pregnant,
                'first_pass_total': total_first_pass_total,
                'preg_recheck_count': total_preg_recheck_count,
                'net_open': total_net_open,
                'net_pregnant': total_net_pregnant,
                'pct_pregnant': f"{avg_pct:.1f}%",
                'is_totals': True,
            }
        else:
            totals_row = None

        context = {
            'breeding_season': breeding_season,
            'rows': rows,
            'totals': totals_row,
        }
        return render(request, 'preg_check/report-5.html', context)


class PregCheckRollingAverageReport(View):
    """
    Rolling 4-year average pregnancy rates by age class.
    Displays pregnancy rates for each age class across recent breeding seasons
    and computes a rolling 4-year average.
    """

    def get(self, request, *args, **kwargs):
        """Orchestrate the rolling average report generation."""
        breeding_season = request.GET.get('breeding_season')
        if not breeding_season:
            breeding_season = CurrentBreedingSeason.load().breeding_season
        
        # Get breeding seasons
        seasons_list = self._get_breeding_seasons(breeding_season)
        if not seasons_list:
            return render(request, 'preg_check/rolling-average-report.html', {
                'seasons': [],
                'rows': [],
            })
        
        # Calculate pregnancy rates by season and age
        pregnancy_rates_by_season_and_age = self._calculate_pregnancy_rates_by_season_and_age_for_pregchecks_with_cows(seasons_list)

        pregnancy_rates_by_season_and_age_for_NO_cow_pregchecks = self._calculate_pregnancy_rates_by_season_and_age_for_pregchecks_with_NO_cows(seasons_list)

        # Get all ages
        all_ages = self._get_all_ages(pregnancy_rates_by_season_and_age)
        if not all_ages:
            return render(request, 'preg_check/rolling-average-report.html', {
                'seasons': seasons_list,
                'rows': [],
            })
        
        # Build report rows
        rows_for_pregchecks_with_cows = self._build_report_rows(all_ages, seasons_list, pregnancy_rates_by_season_and_age)
        rows_for_pregchecks_with_NO_cows = self._build_report_rows([None], seasons_list, pregnancy_rates_by_season_and_age_for_NO_cow_pregchecks)

        # Calculate totals row
        totals_row_for_pregchecks_with_cows = self._calculate_totals_row(all_ages, seasons_list, pregnancy_rates_by_season_and_age)

        context = {
            'seasons': seasons_list,
            'rows': rows_for_pregchecks_with_cows,
            'no_cow_rows': rows_for_pregchecks_with_NO_cows,
            'totals': totals_row_for_pregchecks_with_cows,
            'breeding_season': breeding_season
        }
        return render(request, 'preg_check/rolling-average-report.html', context)


    # def _breeding_season(self):

    def _get_breeding_seasons(self, breeding_season=None):
        """
        Retrieve and sort breeding seasons.
        Returns list of up to 4 most recent seasons, sorted ascending.
        """
        if not breeding_season:
            breeding_season = CurrentBreedingSeason.load().breeding_season
           
        if not isinstance(breeding_season, (int, str)):
            breeding_season = PregCheck.objects.aggregate(
                max_breeding_season=Max('breeding_season')
            )['max_breeding_season']

        if not breeding_season:
            return None

        breeding_season_int = int(breeding_season)
        seasons = list(range(breeding_season_int - 4, breeding_season_int + 1))

        if not PregCheck.objects.filter(breeding_season__in=seasons).exists():
            return None
        
        seasons_list = sorted(list(seasons), reverse=True)[:4]  # Get last 4 seasons
        seasons_list.sort()  # Sort ascending for display order
        return seasons_list

    def _calculate_pregnancy_rates_by_season_and_age_for_pregchecks_with_cows(self, seasons_list):
        pregchecks = PregCheck.objects.exclude(
            cow=None  # we do not want cowless pregchecks factored into the stats
        ).select_related('cow').order_by('cow__ear_tag_id', '-check_date')
        return self._calculate_pregnancy_rates_by_season_and_age(seasons_list, pregchecks)

    def _calculate_pregnancy_rates_by_season_and_age_for_pregchecks_with_NO_cows(self, seasons_list):
        pregchecks = PregCheck.objects.filter(
            cow=None
        ).order_by('-check_date')
        return self._calculate_pregnancy_rates_by_season_and_age(seasons_list, pregchecks)

    def _calculate_pregnancy_rates_by_season_and_age(self, seasons_list, pregchecks):
        """
        Calculate pregnancy rates by season and age.
        Returns dict: {season: {age: pregnancy_rate}}
        """
        pregnancy_rates_by_season_and_age = {}
        
        for season in seasons_list:
            pregnancy_rates_by_season_and_age[season] = {}
            
            # Get all pregchecks for this season
            season_pregchecks = pregchecks.filter(
                breeding_season=season
            )

            # Group by cow to get last check only
            last_check_by_cow = {}
            for pc in season_pregchecks:
                cow_key = None
                if pc.cow and pc.cow.birth_year is not None:
                    cow_key = f"cow-{pc.cow.id}"
                else:
                    cow_key = f"precheck-{pc.id}" # pregchecks where there is no sufficietn cow id, will used preg check id as proxy for counting purposes

                if cow_key not in last_check_by_cow:
                    last_check_by_cow[cow_key] = pc
            
            # Aggregate by birth year (which becomes age class for this season)
            stats_by_birth_year = {}
            for pc in last_check_by_cow.values():
                age = None
                if pc.cow and pc.cow.birth_year is not None:
                    birth_year = pc.cow.birth_year
                    age = season - birth_year
                    
                entry = stats_by_birth_year.setdefault(age, {
                    'total': 0,
                    'pregnant': 0,
                })
                entry['total'] += 1
                if pc.is_pregnant:
                    entry['pregnant'] += 1
            
            # Convert to pregnancy rates
            for age, counts in stats_by_birth_year.items():
                preg_rate = (counts['pregnant'] / counts['total'] * 100) if counts['total'] > 0 else 0
                pregnancy_rates_by_season_and_age[season][age] = {
                    'pregnant': counts['pregnant'],
                    'rate': preg_rate,
                    'count': counts['total']
                }
        
        return pregnancy_rates_by_season_and_age
    
    def _get_all_ages(self, pregnancy_rates_by_season_and_age):
        """
        Determine all age classes present across all seasons.
        Returns sorted list of ages.
        """
        all_ages = set()
        for season_rates in pregnancy_rates_by_season_and_age.values():
            all_ages.update(season_rates.keys())
        if None in all_ages:
            return sorted([a for a in all_ages if a is not None]) + [None]
        return sorted(list(all_ages))
    
    def _build_report_rows(self, all_ages, seasons_list, pregnancy_rates_by_season_and_age):
        """
        Build report rows with season rates and rolling averages.
        Returns list of row dicts with age and rate data.
        """
        rows = []
        for age in all_ages:
            row = {
                'age': age,
                'season_rates': [],
                'year_rates': []
            }
            
            for season in seasons_list:
                rate_dict = pregnancy_rates_by_season_and_age[season].get(age, None)
                if rate_dict is not None:
                    rate = rate_dict['rate']
                    rate_dict['rate'] = f"{rate:.1f}%"
                    row['season_rates'].append(rate_dict)
                    row['year_rates'].append(rate)
                else:
                    row['season_rates'].append("—")
            
            # Calculate rolling 4-year average (average of available years)
            if row['year_rates']:
                rolling_avg = sum(row['year_rates']) / len(row['year_rates'])
                row['rolling_avg'] = f"{rolling_avg:.1f}%"
            else:
                row['rolling_avg'] = "—"
            rows.append(row)
        return rows
    
    def _calculate_totals_row(self, all_ages: list, seasons_list: list, pregnancy_rates_by_season_and_age: dict):
        """
        Returns dict with aggregated data or None if no rows.
        """
        # For each season, calculate the average pregnancy rate across all ages
        season_averages = []
        for season in seasons_list:
            season_dict = pregnancy_rates_by_season_and_age.get(season)
            if not season_dict:
                season_averages.append('-')
                continue

            # Group by cow to get last check only
            stats = {
                'herd_total': 0,
                'pregnant': 0
            }
            for age in all_ages:
                age_dict = season_dict.get(age)
                if age_dict is None:
                    continue
                stats['herd_total'] += age_dict['count']
                stats['pregnant'] += age_dict['pregnant']
            preg_rate = (stats['pregnant'] / stats['herd_total'] * 100) if stats['herd_total'] > 0 else 0
            season_averages.append(
                {
                    'rate': preg_rate,
                    'count': stats['herd_total']
                }
            )        

        actual_season_averages = [a['rate'] for a in season_averages if a != '-']
        if actual_season_averages:
            overall_rolling_avg = sum(actual_season_averages) / len(actual_season_averages)
            overall_rolling_avg_str = f"{overall_rolling_avg:.1f}%"
        else:
            overall_rolling_avg_str = "-"
        return {
            'age': 'AVERAGE',
            'season_rates': [{'rate': f"{s['rate']:.1f}%", 'count': s['count']} if s != '-' else s for s in season_averages],
            'rolling_avg': overall_rolling_avg_str,
        }


class ReportsHubView(View):
    """Hub page to display available reports"""
    def get(self, request, *args, **kwargs):
        reports = [
            {
                'name': 'Summary by Birth Year',
                'url': 'pregcheck-report-5',
                'description': 'Detailed breakdown of pregnancy status by cow birth year/age class for the selected breeding season.'
            },
            {
                'name': 'Rolling Average Report',
                'url': 'pregcheck-rolling-average-report',
                'description': 'Four-year rolling average pregnancy rates for each age class across the herd.'
            },
        ]
        context = {
            'reports': reports,
        }
        return render(request, 'preg_check/reports-hub.html', context)


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
            # Return form errors as JSON for AJAX
            errors = {}
            for field, field_errors in form.errors.items():
                if field == '__all__':
                    errors['form'] = list(field_errors)
                else:
                    errors[field] = list(field_errors)
            return JsonResponse({'errors': errors}, status=400)

class PregCheckDetailView(View):

    def get(self, request, pregcheck_id):
        # Retrieve the PregCheck object or return a 404 response if not found
        pregcheck = get_object_or_404(PregCheck, pk=pregcheck_id)
        pregcheck_details = {
            'id': pregcheck.id,
            'is_pregnant': pregcheck.is_pregnant,
            'check_date': pregcheck.check_date,
            'breeding_season': pregcheck.breeding_season,
            'comments': pregcheck.comments,
            'recheck': pregcheck.recheck,
            'should_sell': pregcheck.should_sell,
        }
        cow = pregcheck.cow
        if cow:
            pregcheck_details.update({
                'ear_tag_id': cow.ear_tag_id,
                'rfid': cow.eid,
                'animal_birth_year': cow.birth_year,
            })

        return JsonResponse(pregcheck_details)
