from django.db import models
from django.utils import timezone


class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class CurrentBreedingSeason(SingletonModel):
    breeding_season = models.PositiveIntegerField()

    def __repr__(self):
        return f"Current Breeding Season: {self.breeding_season}"

    def __str__(self):
        return self.__repr__()
    
    @classmethod
    def load(cls):
        from datetime import datetime
        obj, created = cls.objects.get_or_create(
            pk=1, 
            defaults={'breeding_season': datetime.now().year}
        )
        return obj


class Cow(models.Model):
    ear_tag_id = models.CharField(max_length=10)
    birth_year = models.IntegerField(blank=True, null=True)
    eid = models.CharField(max_length=20, blank=True, null=True, unique=True)
    comments = models.TextField(blank=True)

    created_on = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __repr__(self):
        return f'"{self.ear_tag_id}-{self.birth_year}"'

    def __str__(self):
        return self.__repr__()

    class Meta:
        unique_together = [['ear_tag_id', 'birth_year']]


class PregCheck(models.Model):
    breeding_season = models.IntegerField()
    check_date = models.DateField(null=True, blank=True)
    comments = models.TextField(blank=True)
    cow = models.ForeignKey('Cow', on_delete=models.CASCADE, blank=True, null=True)
    is_pregnant = models.BooleanField(null=True)
    recheck = models.BooleanField(default=False)

    created_on = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __repr__(self):
        preg_status = {True: 'Pregnant', False: 'Open'}.get(self.is_pregnant, 'None')
        return f'{self.cow} - {preg_status} - {self.check_date}'

    def __str__(self):
        return self.__repr__()
