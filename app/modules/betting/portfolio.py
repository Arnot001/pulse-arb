class PortfolioBuilder:
    def __init__(self, horses):
        self.horses = list(horses)
        self.exposure = {}

    def horse_name(self, horse):
        return horse.get("horse")

    def get_exposure(self, horse):
        return self.exposure.get(self.horse_name(horse), 0)

    def add_exposure(self, horse):
        name = self.horse_name(horse)

        if name:
            self.exposure[name] = self.exposure.get(name, 0) + 1

    def exposure_penalty(self, horse):
        used = self.get_exposure(horse)
        rec = horse.get("recommendation_score", 0)

        if used == 0:
            return 0

        if rec >= 96:
            return used * 4

        if rec >= 90:
            return used * 7

        return used * 12

    def adjusted_score(self, horse):
        return horse.get("recommendation_score", 0) - self.exposure_penalty(horse)

    def pick_best(self, used_races=None, min_score=0):
        used_races = set(used_races or [])

        candidates = [
            horse for horse in self.horses
            if horse.get("race_id") not in used_races
            and self.adjusted_score(horse) >= min_score
        ]

        if not candidates:
            return None

        pick = max(candidates, key=self.adjusted_score)
        self.add_exposure(pick)
        return pick

    def build_bet(self, size, min_score=0):
        picks = []
        used_races = set()

        for _ in range(size):
            pick = self.pick_best(
                used_races=used_races,
                min_score=min_score,
            )

            if not pick:
                break

            picks.append(pick)

            if pick.get("race_id"):
                used_races.add(pick.get("race_id"))

        return picks

    def build_portfolio(self):
        best_single = self.build_bet(size=1, min_score=80)
        safe_singles = self.build_bet(size=3, min_score=75)
        best_double = self.build_bet(size=2, min_score=80)
        best_treble = self.build_bet(size=3, min_score=78)

        dominant_pool = [
            horse for horse in self.horses
            if horse.get("recommendation_score", 0) >= 90
        ]

        dominant_builder = PortfolioBuilder(dominant_pool)

        dominant_double = dominant_builder.build_bet(size=2, min_score=90)

        return {
            "best_single": best_single,
            "safe_singles": safe_singles,
            "best_double": best_double,
            "best_treble": best_treble,
            "dominant_double": dominant_double,
            "exposure": self.exposure_report(),
            "portfolio_quality": self.portfolio_quality(),
        }

    def exposure_report(self):
        total = sum(self.exposure.values()) or 1

        rows = []

        for horse, count in sorted(
            self.exposure.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            rows.append({
                "horse": horse,
                "count": count,
                "share": round((count / total) * 100),
            })

        return rows

    def portfolio_quality(self):
        if not self.exposure:
            return 0

        total_uses = sum(self.exposure.values())
        unique_horses = len(self.exposure)

        diversification = round((unique_horses / total_uses) * 100)

        overexposed = max(self.exposure.values())

        if overexposed <= 2:
            exposure_score = 100
        elif overexposed == 3:
            exposure_score = 85
        else:
            exposure_score = 65

        quality = round(
            diversification * 0.55
            + exposure_score * 0.45
        )

        return max(0, min(100, quality))