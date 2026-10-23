"""Tests for the FavoriteLocation model (FR-10 AC-1/5/6, NFR-PERF-6, NFR-REL-3)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from weather.models import FavoriteLocation
from weather.services.domain import Location

AMARILLO = Location("Amarillo", "Texas", "US", 35.2219971, -101.8312969)


def place(index: int) -> Location:
    return Location(f"Place {index}", "", "US", 10 + index / 10, -100 - index / 10)


class FavoriteLocationModelTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="Correct-Horse-91")
        self.bob = User.objects.create_user("bob", password="Correct-Horse-91")

    def test_fr10_ac1_stores_owner_place_coordinates_and_date_added(self):
        favorite = FavoriteLocation.add(self.alice, AMARILLO)
        favorite.refresh_from_db()
        self.assertEqual(favorite.user, self.alice)
        self.assertEqual(
            (favorite.name, favorite.state, favorite.country), ("Amarillo", "Texas", "US")
        )
        self.assertIsNotNone(favorite.created_at)

    def test_fr10_ac5_coordinates_are_rounded_to_four_decimals(self):
        favorite = FavoriteLocation.add(self.alice, AMARILLO)
        favorite.refresh_from_db()
        self.assertEqual(favorite.latitude, Decimal("35.2220"))
        self.assertEqual(favorite.longitude, Decimal("-101.8313"))

    def test_round_coordinate_rounds_half_up(self):
        self.assertEqual(FavoriteLocation.round_coordinate(1.00005), Decimal("1.0001"))
        self.assertEqual(FavoriteLocation.round_coordinate(-1.00005), Decimal("-1.0001"))
        self.assertEqual(FavoriteLocation.round_coordinate("90"), Decimal("90.0000"))

    def test_to_location_returns_the_value_object(self):
        favorite = FavoriteLocation.add(self.alice, AMARILLO)
        self.assertEqual(
            favorite.to_location(), Location("Amarillo", "Texas", "US", 35.222, -101.8313)
        )

    def test_fr10_ac5_same_rounded_coordinates_cannot_be_saved_twice(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        nearby = Location("Amarillo again", "Texas", "US", 35.22204, -101.83126)
        with self.assertRaises(FavoriteLocation.AlreadySaved):
            FavoriteLocation.add(self.alice, nearby)
        self.assertEqual(FavoriteLocation.objects.filter(user=self.alice).count(), 1)

    def test_fr10_ac5_database_enforces_uniqueness_per_user(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FavoriteLocation.objects.create(
                user=self.alice, name="Copy", latitude=Decimal("35.2220"),
                longitude=Decimal("-101.8313"),
            )

    def test_fr10_ac2_different_users_can_save_the_same_place(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        FavoriteLocation.add(self.bob, AMARILLO)
        self.assertEqual(FavoriteLocation.objects.count(), 2)

    def test_fr10_ac6_at_most_twenty_favorites_per_user(self):
        self.assertEqual(FavoriteLocation.MAX_PER_USER, 20)
        for index in range(20):
            FavoriteLocation.add(self.alice, place(index))
        with self.assertRaises(FavoriteLocation.LimitReached):
            FavoriteLocation.add(self.alice, place(20))
        self.assertEqual(FavoriteLocation.objects.filter(user=self.alice).count(), 20)
        # The limit is per user.
        FavoriteLocation.add(self.bob, place(20))

    def test_fr10_ac5_duplicate_is_reported_before_the_limit(self):
        for index in range(20):
            FavoriteLocation.add(self.alice, place(index))
        with self.assertRaises(FavoriteLocation.AlreadySaved):
            FavoriteLocation.add(self.alice, place(3))

    def test_nfr_rel3_failed_add_leaves_no_partial_record(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        before = FavoriteLocation.objects.count()
        with self.assertRaises(FavoriteLocation.AlreadySaved):
            FavoriteLocation.add(self.alice, AMARILLO)
        self.assertEqual(FavoriteLocation.objects.count(), before)

    def test_favorites_are_deleted_with_their_owner(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        self.alice.delete()
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_listed_in_the_order_they_were_added(self):
        first = FavoriteLocation.add(self.alice, place(2))
        second = FavoriteLocation.add(self.alice, place(1))
        self.assertEqual(list(FavoriteLocation.objects.filter(user=self.alice)), [first, second])

    def test_nfr_perf6_uniqueness_constraint_is_declared(self):
        constraints = {c.name: c for c in FavoriteLocation._meta.constraints}
        constraint = constraints["unique_favorite_per_user"]
        self.assertEqual(tuple(constraint.fields), ("user", "latitude", "longitude"))

    def test_str_names_the_place(self):
        self.assertEqual(str(FavoriteLocation.add(self.alice, AMARILLO)), "Amarillo, Texas, US")
