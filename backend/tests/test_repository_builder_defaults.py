"""Dependency-free checks for defaults in the original builder form."""
import unittest
from copy import deepcopy

from app.services.repository_builder_defaults import omit_unchanged_defaults


class BuilderDefaultsTests(unittest.TestCase):
    def test_unchanged_shared_values_are_omitted(self):
        entry = {
            "mirror": {"archive_url": "https://example.org", "max_tries": 3},
            "schedule": {"enabled": True, "type": "weekly"},
        }
        defaults = {"mirror": {"max_tries": 3}, "schedule": {"enabled": True, "type": "weekly"}}
        before = deepcopy(defaults)
        omit_unchanged_defaults(entry, defaults)
        self.assertEqual(entry, {"mirror": {"archive_url": "https://example.org"}})
        self.assertEqual(defaults, before)

    def test_changed_value_is_saved(self):
        entry = {"retention": {"keep_last": 10}}
        omit_unchanged_defaults(entry, {"retention": {"keep_last": 7}})
        self.assertEqual(entry, {"retention": {"keep_last": 10}})

    def test_disabled_schedule_remains_explicit(self):
        entry = {"schedule": {"enabled": False, "type": "weekly"}}
        omit_unchanged_defaults(entry, {"schedule": {"enabled": True, "type": "weekly"}})
        self.assertEqual(entry, {"schedule": {"enabled": False}})

    def test_optional_empty_and_unknown_fields(self):
        entry = {"publish": {"gpg_key": "", "prefix": "debian", "extra": "keep"}}
        omit_unchanged_defaults(entry, {"publish": {"gpg_key": None}})
        self.assertEqual(entry, {"publish": {"prefix": "debian", "extra": "keep"}})


if __name__ == "__main__":
    unittest.main()
