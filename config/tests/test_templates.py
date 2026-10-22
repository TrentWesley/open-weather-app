"""Tests for the project base template and error pages (NFR-FT-7, NFR-AC-2, NFR-AC-9)."""
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase
from django.views.defaults import server_error


class NotFoundPageTests(SimpleTestCase):
    def setUp(self):
        self.response = self.client.get("/this-page-does-not-exist/")

    def test_returns_404_with_custom_template(self):
        self.assertEqual(self.response.status_code, 404)
        self.assertTemplateUsed(self.response, "404.html")
        self.assertTemplateUsed(self.response, "base.html")

    def test_links_back_to_home(self):
        self.assertContains(self.response, 'href="/"', status_code=404)


class BaseTemplateTests(SimpleTestCase):
    """The base layout is checked through the 404 page, which extends it."""

    def setUp(self):
        self.response = self.client.get("/missing/")

    def assertInPage(self, fragment):
        self.assertContains(self.response, fragment, status_code=404)

    def test_declares_language(self):
        self.assertInPage('<html lang="en">')

    def test_has_viewport_meta(self):
        self.assertInPage('name="viewport"')

    def test_has_semantic_landmarks(self):
        for tag in ("<header", "<nav", '<main id="main-content"', "<footer"):
            with self.subTest(tag=tag):
                self.assertInPage(tag)

    def test_has_skip_link_as_first_focusable_element(self):
        body = self.response.content.decode()
        skip = body.find('href="#main-content"')
        self.assertNotEqual(skip, -1)
        self.assertLess(skip, body.find("<nav"))

    def test_has_polite_live_region(self):
        self.assertInPage('id="live-region"')
        self.assertInPage('aria-live="polite"')

    def test_links_site_stylesheet(self):
        self.assertInPage(f'href="{settings.STATIC_URL}css/site.css"')


class ServerErrorPageTests(SimpleTestCase):
    def test_renders_custom_500_page(self):
        request = RequestFactory().get("/")
        response = server_error(request)
        content = response.content.decode()
        self.assertEqual(response.status_code, 500)
        self.assertIn('<main id="main-content"', content)
        self.assertIn('href="/"', content)
        self.assertNotIn("Traceback", content)


class StaticFilesTests(SimpleTestCase):
    def test_site_stylesheet_is_discoverable(self):
        self.assertIsNotNone(finders.find("css/site.css"))
