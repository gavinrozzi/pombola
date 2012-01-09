import datetime

from django.core.management.base import NoArgsCommand

from hansard.models import Alias

class Command(NoArgsCommand):
    help = 'List all the speaker names that have not been matched up to a real person'
    args = ''

    def handle_noargs(self, **options):

        unassigned = Alias.objects.all().unassigned()
        count = unassigned.count()
        
        if count:
            print "There are %u Hansard speaker names that could not be matched to a person" % count
            print ""

            for alias in unassigned:
                print "\t'%s'" % alias.alias

