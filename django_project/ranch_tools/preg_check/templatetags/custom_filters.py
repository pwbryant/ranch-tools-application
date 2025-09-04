from django import template

register = template.Library()

@register.filter
def has_comments(pregchecks):
    return any(pregcheck.comments for pregcheck in pregchecks)

