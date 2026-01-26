from django.contrib import admin

from .models import Cow, PregCheck


@admin.register(Cow)
class CowAdmin(admin.ModelAdmin):
    list_display = ('ear_tag_id', 'eid', 'birth_year')
    list_filter = ('birth_year',)
    search_fields = ('ear_tag_id', 'eid', 'birth_year')
    fields = ('eid', 'ear_tag_id', 'birth_year', 'comments',)


@admin.register(PregCheck)
class PregCheckAdmin(admin.ModelAdmin):
    list_display = ('cow', 'check_date', 'is_pregnant')
    list_filter = ('is_pregnant', 'check_date', 'breeding_season')
    search_fields = ('cow__ear_tag_id', 'cow__eid', 'breeding_season')
