from django.test import TestCase

from .models import Slide

class ModelTest(TestCase):

    fixtures = ['test_data.json']

    def test_active(self):
        self.assertEqual(
            set(
                Slide.objects.all().active().values_list('id', flat=True)
            ),
            set([1, 3])
        )

    def test_inactive(self):
        self.assertEqual(
            set(
                Slide.objects.all().inactive().values_list('id', flat=True)
            ),
            set([2])
        )

    def test_random_slide(self):
        """
        Test that we get back a random active slide. Do this by running many
        times and then checking that all activo slides are in the returned data.
        """

        seen_slide_ids = set()

        for i in range(100):
            slide = Slide.objects.random_slide()
            seen_slide_ids.add(slide.id)

        for slide in Slide.objects.all().active():
            self.assertTrue(slide.id in seen_slide_ids)
        for slide in Slide.objects.all().inactive():
            self.assertFalse(slide.id in seen_slide_ids)


        # Delete all the slides and then check that random_slide returns None
        Slide.objects.all().delete()

        self.assertEqual(
            Slide.objects.random_slide(),
            None
        )

    def test_template_name(self):
        # test a known slide
        self.assertEqual(
            Slide.objects.get(id=1).template_name,
            'spinner/slides/quote-content.html'
        )

        # create a slide that is for a content_type that would never be used in a spinner. A slide of a slide should be suitable :)
        slide = Slide.objects.all()[0]
        slide_of_slide = Slide.objects.create(sort_order=0, content_object=slide)

        # Test that the desired template is given, even if it does not exist
        # (used in default.html template to tell template outhors what to do)
        self.assertEqual(
            slide_of_slide.required_template_name,
            'spinner/slides/slide.html'
        )

        # Test that the default is returned
        self.assertEqual(
            slide_of_slide.template_name,
            'spinner/slides/default.html'
        )
