import re

from django.db import models

from pombola.core.models import Person
from pombola.hansard.models import Sitting, Alias
from pombola.hansard.models.base import HansardModelBase

from pombola.hansard.constants import NAME_SUBSTRING_MATCH, NAME_SET_INTERSECTION_MATCH


class EntryQuerySet(models.query.QuerySet):
    def monthly_appearance_counts(self):
        """Return an list of dictionaries for dates and counts for each month"""

        # would prefer to do this as a single query but I can't seem to make the ORM do that.

        dates = self.dates('sitting__start_date','month', 'DESC')
        counts = []

        for d in dates:
            qs = self.filter(sitting__start_date__month=d.month, sitting__start_date__year=d.year)
            counts.append(dict(date=d, count=qs.count()))

        return counts

    def unassigned_speeches(self):
        """All speeches that do not have a speaker assigned"""
        return self.filter(
            speaker__isnull = True,
            type            = 'speech',
        ).exclude(
            speaker_name = '',
        )


class Entry(HansardModelBase):
    """Model for representing an entry in Hansard - speeches, headings etc"""

    type_choices = (
        ('heading', 'Heading'),
        ('scene',   'Description of event'),
        ('speech',  'Speech'),
        ('other',   'Other'),
    )

    type          = models.CharField( max_length=20, choices=type_choices )
    sitting       = models.ForeignKey( Sitting )

    # page_number is the page that this appeared on in the source.
    page_number   = models.IntegerField( blank=True )

    # Doesn't really mean anything - just a counter so that for each sitting we
    # can display the entries in the correct order.
    text_counter  = models.IntegerField()

    # Speakers only apply to the 'speech' type. For those we should always have
    # a name and possibly a title. Other code may then take those and try to
    # link the speech up to a person.
    speaker_name  = models.CharField( max_length=200, blank=True )
    speaker_title = models.CharField( max_length=200, blank=True )
    speaker       = models.ForeignKey( Person, blank=True, null=True, related_name='hansard_entries' )

    # What was actually said
    content       = models.TextField()

    objects = EntryQuerySet.as_manager()

    def __unicode__(self):
        return "%s: %s" % (self.type, self.content[:100])

    def get_absolute_url(self):
        sitting_url = self.sitting.get_absolute_url()
        return "%s#entry-%u" % (sitting_url, self.id)

    def css_class(self):
        return 'hansard_entry'

    class Meta:
        ordering = ['sitting', 'text_counter']
        app_label = 'hansard'
        verbose_name_plural = 'entries'

    @classmethod
    def assign_speakers(cls, name_matching_algorithm=NAME_SET_INTERSECTION_MATCH):
        """Go through all entries and assign speakers"""

        entries = cls.objects.all().unassigned_speeches()

        # create an in memory cache of speaker names and the sitting dates, to
        # avoid hitting the db as badly with all the repeated requests
        cache = {}

        for entry in entries:
            cache_key = "%s-%s" % (entry.sitting.start_date, entry.speaker_name)

            if cache_key in cache:
                speakers = cache[cache_key]
            else:
                speakers = entry.possible_matching_speakers(
                    update_aliases=True,
                    name_matching_algorithm=name_matching_algorithm,
                    )
                cache[cache_key] = speakers

            if speakers and len(speakers) == 1:
                speaker = speakers[0]
                entry.speaker = speaker
                entry.save()

    def alias_match_score(self, name_one, name_two):
        """
        Return a score based on the intersection of two names including titles
        minus all punctuation.
        """
        set_one = set(filter(lambda item : len(item) > 1, re.sub('[^A-Za-z]',' ', name_one).split()))
        set_two = set(filter(lambda item : len(item) > 1, re.sub('[^A-za-z]',' ', name_two).split()))
        return len(set_one & set_two)

    def possible_matching_speakers(self, update_aliases=False, name_matching_algorithm=NAME_SET_INTERSECTION_MATCH):
        """
        Return array of person objects that might be the speaker.

        If 'update_aliases' is True (False by default) and the name cannot be
        ignored then an entry will be made in the alias table that so that the
        alias is inspected by an admin.
        """

        name = self.speaker_name
        name = Alias.clean_up_name( name )

        # First check for a matching alias that is not ignored
        try:
            alias = Alias.objects.get( alias=name )

            if alias.ignored:
                # if the alias is ignored we should not match anything
                return []
            elif alias.person:
                return [ alias.person ]
            elif alias.is_unassigned:
                # Pretend that this alias does not exist so that it is checked
                # in case new people have been added to the database since the
                # last run.
                pass
            else:
                return []

        except Alias.DoesNotExist:
            alias = None

        person_search = (
            Person
            .objects
            .all()
            .is_politician( when=self.sitting.start_date )
            .exclude(hidden=True)
            .distinct()
        )

        if name_matching_algorithm == NAME_SUBSTRING_MATCH:
            # drop the prefix
            stripped_name = re.sub(r'^\w+\.\s', '', name)
            person_search = person_search.filter(legal_name__icontains=stripped_name)

            # if the results are ambiguous, try restricting to members of the current house
            # unless it's a joint sitting, in which case this is dangerous
            #
            # FIXME: (1) the position filter currently checks whether a person has *ever* held
            #        a qualifying position, would be better if this were a check against
            #        whether the position was held at date of the sitting.
            #
            #        (2) it might also be interesting to have an optional Pombola Organisation
            #        associated with a Sitting so that it would be easier to check whether the
            #        Person has a matching association with an Organisation rather than checking
            #        PositionTitle names (not sure what would happen with Joint Sittings - dual association?)

            if len(person_search) > 1 and 'Joint Sitting' not in self.sitting.source.name:
                if self.sitting.venue.name == 'Senate':
                    current_house = person_search.filter(position__title__name__contains='Senator')
                else:
                    current_house = person_search.filter(position__title__name__contains=self.sitting.venue.name)
                if current_house:
                    person_search = current_house

        results = person_search.all()[0:]

        if name_matching_algorithm == NAME_SET_INTERSECTION_MATCH:
            results = sorted(
                [i for i in results if self.alias_match_score('%s %s'%(i.title, i.legal_name), name) > 1],
                key=lambda x: self.alias_match_score('%s %s'%(x.title, x.legal_name), name),
                reverse=True,
                )

        found_one_result = len(results) == 1

        # If there is a single matching speaker and an unassigned alias delete it
        if found_one_result and alias and alias.is_unassigned:
            alias.delete()

        # create an entry in the aliases table if one is needed
        if not alias and update_aliases and not found_one_result and not Alias.can_ignore_name(name):
            Alias.objects.create(
                alias   = name,
                ignored = False,
                person  = None,
            )

        return results
