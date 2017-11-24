from everypolitician import EveryPolitician

from django.core.management.base import BaseCommand

from pombola.core.models import Person


class Command(BaseCommand):
    help = 'Sync EveryPolitician UUID to Person.everypolitician_uuid field'

    def handle(self, **options):
        verbose_level = options['verbosity']

        # FIXME: This SHA is currently pointing at a branch which has the
        # `peoples_assembly` identifier, but this isn't on master because
        # South Africa is broken in EveryPolitician at the moment.
        #
        # TODO: Make this SHA configurable.
        url = ('https://cdn.rawgit.com/everypolitician/everypolitician-data/'
               'eaa170a15d61b024b49e22527fd1fdf6eba18ee6/countries.json')

        ep = EveryPolitician(countries_json_url=url)
        south_africa_assembly = ep.country('South-Africa').legislature('Assembly').popolo()

        id_lookup = {}
        for popolo_person in south_africa_assembly.persons:
            pa_ids = [i for i in popolo_person.identifiers if i['scheme'] == 'peoples_assembly']
            if pa_ids == []:
                continue
            id_lookup[pa_ids[0]['identifier']] = popolo_person.id

        error_msg = u"No EveryPolitician UUID found for {} {} https://www.pa.org.za/person/{}/\n"
        for person in Person.objects.filter(hidden=False):
            uuid = id_lookup.get(str(person.id))
            if uuid is None:
                if verbose_level > 1:
                    self.stderr.write(error_msg.format(person.id, person.name, person.slug))
                continue
            identifier, created = person.identifiers.get_or_create(
                scheme='everypolitician',
                identifier=uuid,
            )
            if verbose_level > 0:
                if created:
                    msg = u"Created new identifier for {}: {}"
                else:
                    msg = u"Existing identifier found for {}: {}"
                self.stdout.write(msg.format(person.name, identifier.identifier))
