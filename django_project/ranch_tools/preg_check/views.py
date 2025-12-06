from datetime import datetime, timezone
import json
from urllib.parse import urlencode

from django.db.models import F, Q
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
        # Get all unique breeding seasons in descending order
        all_seasons = PregCheck.objects.values_list('breeding_season', flat=True).distinct().order_by('-breeding_season')
        if not all_seasons.exists():
            # No data available
            return render(request, 'preg_check/rolling-average-report.html', {
                'seasons': [],
                'rows': [],
            })
        
        seasons_list = sorted(list(all_seasons), reverse=True)[:4]  # Get last 4 seasons
        seasons_list.sort()  # Sort ascending for display order
        
        # Collect all unique birth years across all seasons
        all_cows = Cow.objects.filter(pregcheck__isnull=False).distinct()
        birth_years = set()
        for cow in all_cows:
            if cow.birth_year is not None:
                birth_years.add(cow.birth_year)
        
        # For each season, calculate pregnancy rates by age class
        pregnancy_rates_by_season_and_age = {}
        for season in seasons_list:
            pregnancy_rates_by_season_and_age[season] = {}
            
            # Get all pregchecks for this season
            season_pregchecks = PregCheck.objects.filter(
                breeding_season=season
            ).select_related('cow').order_by('cow_id', 'check_date', 'created_on')
            
            # Group by cow to get first check only
            first_check_by_cow = {}
            for pc in season_pregchecks:
                if pc.cow and pc.cow.birth_year is not None:
                    cow_key = f"cow-{pc.cow.id}"
                    if cow_key not in first_check_by_cow:
                        first_check_by_cow[cow_key] = pc
            
            # Aggregate by birth year (which becomes age class for this season)
            stats_by_birth_year = {}
            for pc in first_check_by_cow.values():
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
                pregnancy_rates_by_season_and_age[season][age] = preg_rate
        
        # Determine the range of ages to display
        all_ages = set()
        for season_rates in pregnancy_rates_by_season_and_age.values():
            all_ages.update(season_rates.keys())
        
        if not all_ages:
            return render(request, 'preg_check/rolling-average-report.html', {
                'seasons': seasons_list,
                'rows': [],
            })
        
        all_ages = sorted(list(all_ages))
        
        # Build the rows
        rows = []
        for age in all_ages:
            row = {
                'age': age,
                'season_rates': [],
                'year_rates': []
            }
            
            for season in seasons_list:
                rate = pregnancy_rates_by_season_and_age[season].get(age, None)
                if rate is not None:
                    row['season_rates'].append(f"{rate:.1f}%")
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
        
        # Calculate totals row - average of each season and overall rolling average
        if rows:
            # For each season, calculate the average pregnancy rate across all ages
            season_averages = []
            for season_idx, season in enumerate(seasons_list):
                season_rates = []
                for row in rows:
                    if season_idx < len(row['year_rates']):
                        # Get the rate for this season from the year_rates list
                        rate_value = row['year_rates'][season_idx] if season_idx < len(row['year_rates']) else None
                        if rate_value is not None:
                            season_rates.append(rate_value)
                
                if season_rates:
                    avg = sum(season_rates) / len(season_rates)
                    season_averages.append(f"{avg:.1f}%")
                else:
                    season_averages.append("—")
            
            # Calculate overall rolling average
            all_rolling_avg_values = []
            for row in rows:
                if row['rolling_avg'] != "—":
                    # Extract numeric value from percentage string
                    avg_str = row['rolling_avg'].replace('%', '')
                    all_rolling_avg_values.append(float(avg_str))
            
            if all_rolling_avg_values:
                overall_rolling_avg = sum(all_rolling_avg_values) / len(all_rolling_avg_values)
                overall_rolling_avg_str = f"{overall_rolling_avg:.1f}%"
            else:
                overall_rolling_avg_str = "—"
            
            totals_row = {
                'age': 'AVERAGE',
                'season_rates': season_averages,
                'year_rates': [float(s.replace('%', '')) if s != "—" else None for s in season_averages],
                'rolling_avg': overall_rolling_avg_str,
            }
        else:
            totals_row = None
        
        context = {
            'seasons': seasons_list,
            'rows': rows,
            'totals': totals_row,
        }
        return render(request, 'preg_check/rolling-average-report.html', context)


class ReportsHubView(View):
    """Hub page to display available reports"""
    def get(self, request, *args, **kwargs):
        reports = [
            {
                'name': 'Report Five — Summary by Birth Year',
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
            errors = form.errors.as_json()
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
        }
        cow = pregcheck.cow
        if cow:
            pregcheck_details.update({
                'ear_tag_id': cow.ear_tag_id,
                'rfid': cow.eid,
                'animal_birth_year': cow.birth_year,
            })

        return JsonResponse(pregcheck_details)
