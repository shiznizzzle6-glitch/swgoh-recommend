"""Counter engine — read an enemy's text, work out what beats it.

Every other analyzer here ranks *your* roster. This one starts from the
opposition: a Conquest trial modifier, an enemy leader ability, anything you can
paste in. It reads that text for the mechanics that make the enemy work, then
names the tools that break each one and finds which of your units actually bring
those tools — quoting the ability line so you can see *why*, not just who.

Two ideas do the work:

`THREATS` — what the enemy text does to you. Each carries a plain-language
reading, the tools that answer it, and (the part that's easy to get wrong) the
tactics that *backfire* against it. A team that heals off your debuffs punishes
the potency squad you'd normally reach for, and nothing in a name-based counter
list would ever tell you that.

`TOOLS` — the counter-mechanics themselves, matched by regex against the text of
every ability in the game, so "who can dispel" is answered from your live roster
rather than a hand-maintained list of names.

The matching is deliberately literal: it finds the sentence that triggered a
match and shows it. Ability text is swgoh.gg's max-tier wording, so a counter
gated behind a zeta you haven't learned is flagged rather than silently trusted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..abilities import ability_defs, is_omicron_learned, is_zeta_learned
from ..ability_text import abilities_of
from ..models import Player
from ..names import display_name
from ..ships import is_ship
from ..trials import modifier_entries, modifier_text, trial, trial_label

# Comlink reports skill tiers 2 below the in-game scale the zeta rules are
# written against (validated in swgoh.recommend.zetas).
COMLINK_TIER_OFFSET = 2

# Bearers listed per tool before the rest are summarised as a count.
MAX_BEARERS = 6

# Quotes are evidence, not documentation — a few kit descriptions run to a dozen
# lines, and pasting one whole buries the line that actually matched.
MAX_QUOTE = 260


@dataclass(frozen=True)
class Tool:
    """A counter-mechanic one of your units can bring."""

    key: str
    label: str
    blurb: str  # what it's good for, in plain language
    patterns: tuple[str, ...]
    # Wording that looks like a match but points the wrong way. Ability text
    # doesn't mark direction, so "Dark Trooper can't be revived" (about himself)
    # reads identically to "enemies can't be revived" without this.
    excludes: tuple[str, ...] = ()


TOOLS: tuple[Tool, ...] = (
    Tool(
        "dispel",
        "Dispel buffs",
        "Strips the buffs an enemy engine runs on. The answer to anything that stacks up before it hits.",
        (r"\bdispel\w*\b[^.]{0,60}\bbuff", r"\bdispel all buffs\b"),
    ),
    Tool(
        "buff_prevention",
        "Buff Immunity / block buffs",
        "Stops the buffs arriving at all — better than dispelling when buffs are being regained every turn.",
        (r"Buff Immunity", r"can'?t gain buffs"),
    ),
    Tool(
        "ability_block",
        "Ability Block",
        "Shuts off specials. Kills combo engines that depend on one key ability.",
        (r"Ability Block",),
    ),
    Tool(
        "stun",
        "Stun",
        "Takes a whole turn away. The bluntest way to stop a unit doing anything at all.",
        (r"\bStun\b", r"\bStunned\b"),
    ),
    Tool(
        "daze",
        "Daze",
        "Blocks assists, counters and bonus Turn Meter — the glue holding most enemy chains together.",
        (r"\bDaze\b", r"\bDazed\b"),
    ),
    Tool(
        "stagger",
        "Stagger",
        "Disrupts the enemy's turn economy without needing to land a full stun.",
        (r"\bStagger\b",),
    ),
    Tool(
        "tm_removal",
        "Turn Meter removal",
        "Denies turns. Fewer enemy turns means fewer stacks, fewer crits, less of everything.",
        (r"remove\s+\d+%?\s+Turn Meter", r"reduce[^.]{0,30}Turn Meter", r"Turn Meter removal"),
    ),
    Tool(
        "healing_immunity",
        "Healing Immunity",
        "Stops recovery. Essential against anything that heals itself back up faster than you burn it down.",
        (r"Healing Immunity",),
    ),
    Tool(
        "crit_chance",
        "Critical Chance / reliable crits",
        "Lands crits on demand — which matters when the rules reward crits rather than punish them.",
        (r"Critical Chance Up", r"gain[s]? \d+% Critical Chance", r"guaranteed to critically hit"),
    ),
    Tool(
        "tm_gain",
        "Turn Meter gain / Speed Up",
        "Moves you up the order without needing raw Speed — the way to act first when the rules slow everyone down.",
        (
            r"Speed Up",
            r"all(?:y|ies)[^.]{0,40}gain \d+% Turn Meter",
            r"gain[s]? \d+% Turn Meter",
            r"\+\d+ Speed",
        ),
    ),
    Tool(
        "crit_avoidance",
        "Critical Avoidance / crit denial",
        "Blunts crit-driven damage and any effect that triggers 'whenever they score a critical hit'.",
        (r"Critical Avoidance", r"can'?t be critically hit", r"Critical Chance Down"),
    ),
    Tool(
        "taunt",
        "Taunt",
        "Chooses who gets hit. Protects a fragile unit and controls which of yours takes the punishment.",
        (r"\bTaunt\b", r"\bTaunting\b"),
    ),
    Tool(
        "foresight",
        "Foresight / evasion",
        "Avoids attacks outright, so on-hit triggers never fire.",
        (r"\bForesight\b", r"Evasion Up"),
    ),
    Tool(
        "tenacity_up",
        "Tenacity Up",
        "Resists incoming debuffs — but useless against anything worded \"can't be resisted\".",
        (r"Tenacity Up",),
    ),
    Tool(
        "cleanse",
        "Cleanse allies",
        "Removes debuffs from your own team — the answer to debuffs being reflected back at you.",
        (r"dispel all debuffs on (?:themselves|all allies|a random|target ally)", r"cleanse"),
    ),
    Tool(
        "protection_up",
        "Protection Up / bonus Protection",
        "Buys survival time against chip damage and Protection drain.",
        (r"Protection Up", r"bonus Protection"),
    ),
    Tool(
        "offense_down",
        "Offense Down",
        "Cuts enemy damage at the source.",
        (r"Offense Down",),
    ),
    Tool(
        "heal",
        "Healing / recovery",
        "Undoes chip damage and reflected damage you can't avoid taking.",
        (r"Heal Over Time", r"recover[s]? \d+% (?:Health|Protection)", r"heal[s]? all allies"),
    ),
    Tool(
        "defense_pen",
        "Defense Penetration / ignore Protection",
        "Punches through tanky enemies and Defense-stacking modifiers.",
        (r"Defense Penetration", r"ignores? (?:their )?Protection", r"Armor Shred"),
    ),
    Tool(
        "revive_block",
        "Prevent revive",
        "Makes a kill stick against anything that revives.",
        # Must be aimed at the enemy. Several kits say a unit or its allies
        # "can't be revived" as their own drawback, which is not a tool.
        (
            r"enem\w+[^.]{0,80}can'?t be revived",
            r"can'?t be revived[^.]{0,40}enem\w+",
            r"defeats?\s+(?:the\s+)?target[^.]{0,60}can'?t be revived",
            r"defeated target can'?t be revived",
        ),
        excludes=(r"all(?:y|ies)[^.]{0,40}can'?t be revived",),
    ),
    Tool(
        "instant_defeat",
        "Instant defeat",
        "Skips health bars entirely — ignores sustain, thresholds and damage gates.",
        # "instantly defeated" is usually passive — something happening *to* a
        # unit — so only the active form counts as a tool you can bring.
        (r"instantly defeat(?!ed\b)",),
    ),
    Tool(
        "cooldown_increase",
        "Increase cooldowns",
        "Delays the enemy's key ability instead of trying to out-damage it.",
        (r"increase[^.]{0,40}cooldown", r"cooldown[s]? (?:are |is )?increased"),
    ),
    Tool(
        "unavoidable",
        "Effects that can't be resisted/evaded",
        "Reliability: lands through Tenacity, Foresight and dodge-based defence.",
        (r"can'?t be (?:resisted|evaded|dispelled|prevented)",),
    ),
)

TOOLS_BY_KEY = {t.key: t for t in TOOLS}


@dataclass(frozen=True)
class Threat:
    """Something the enemy text does, and what to do about it."""

    key: str
    label: str
    patterns: tuple[str, ...]
    means: str  # plain-language reading of the mechanic
    use: tuple[str, ...] = ()  # tool keys that answer it
    avoid: tuple[str, ...] = ()  # tactics that backfire


THREATS: tuple[Threat, ...] = (
    Threat(
        "debuff_feeding",
        "Feeds on your debuffs",
        (
            r"recover[s]?[^.]{0,80}whenever[^.]{0,40}(?:inflicted with|gain)[^.]{0,20}debuff",
            r"whenever[^.]{0,40}debuff[^.]{0,60}(?:recover|heal|gain[s]? \d+% (?:Health|Protection))",
        ),
        "Every debuff you land is healing them. Potency and debuff-stacking — normally your best "
        "tools — actively feed this enemy.",
        use=("instant_defeat", "defense_pen", "healing_immunity", "tm_removal"),
        avoid=(
            "Don't bring a debuff-stacking squad — each debuff you apply converts straight into their sustain.",
            "Don't rely on damage-over-time chip damage; it tops them up faster than it wears them down.",
        ),
    ),
    Threat(
        "debuff_reflect",
        "Reflects your debuffs back",
        (
            r"dispel all debuffs on themselves and inflict those debuffs",
            r"inflict those debuffs on",
        ),
        "Debuffs you land get cleaned off and thrown onto your own team, so heavy debuffing arms "
        "the enemy against you.",
        use=("cleanse", "tenacity_up", "instant_defeat"),
        avoid=(
            "Don't stack debuffs you wouldn't want on your own squad — that's exactly where they end up.",
        ),
    ),
    Threat(
        "buff_feeding",
        "Heals whenever they gain buffs",
        (r"recover[s]?[^.]{0,60}whenever[^.]{0,30}gain[^.]{0,15}buff",),
        "Their own buffs double as healing, so letting the buffs land is letting them heal.",
        use=("buff_prevention", "dispel", "healing_immunity"),
        avoid=("Dispelling alone won't keep up if they regain buffs every turn — prevent the buffs instead.",),
    ),
    Threat(
        "crit_engine",
        "Crit-driven engine",
        (r"scores? a critical hit", r"critically hits?", r"whenever[^.]{0,40}critical"),
        "Their crits are the trigger. Deny the crit and you deny whatever it sets off.",
        use=("crit_avoidance", "foresight", "taunt", "protection_up"),
        avoid=("Don't field squishy, low-Protection units in front — they turn every enemy crit into a snowball.",),
    ),
    Threat(
        "protection_drain",
        "Drains your Protection",
        (r"(?:the )?enemy loses \d+% Protection", r"lose[s]? \d+% (?:Max )?Protection", r"reduce[^.]{0,30}Max Protection"),
        "Percentage Protection loss ignores how tanky you are — big health pools don't save you.",
        use=("protection_up", "taunt", "instant_defeat"),
        avoid=("Don't plan on out-tanking it; percent-based drain scales with your own health bar.",),
    ),
    Threat(
        "armor_shred",
        "Armor Shred / Defense stripping",
        (r"Armor Shred", r"Defense Down"),
        "Your Defense gets stripped for the rest of the fight, so incoming damage climbs the "
        "longer the battle runs.",
        use=("instant_defeat", "taunt", "protection_up"),
        avoid=("Don't play the long grind — a shredded team loses damage races it would normally win.",),
    ),
    Threat(
        "revive",
        "Revives after being defeated",
        (r"\brevive\b", r"\brevived\b", r"return[s]? to life"),
        "Kills don't stick. Burning them down once just resets the clock.",
        use=("revive_block", "instant_defeat", "healing_immunity"),
        avoid=("Don't spread damage evenly — you'll never finish anything through a revive.",),
    ),
    Threat(
        "self_heal",
        "Heals or recovers Protection",
        (r"recover[s]? \d+% (?:Health|Protection)", r"\bheal[s]?\b[^.]{0,30}\d+%"),
        "Sustain outpaces chip damage; you need burst or you need the healing switched off.",
        use=("healing_immunity", "instant_defeat", "defense_pen"),
        avoid=("Don't rely on slow, even chip damage — it gets healed off between turns.",),
    ),
    Threat(
        "stack_engine",
        "Builds stacking power over time",
        (r"\(stacking", r"gain[s]? (?:a|\d+) stack", r"per stack", r"stacking, max"),
        "They get stronger every turn. The fight is on a timer you don't control.",
        use=("tm_removal", "stun", "ability_block", "daze"),
        avoid=("Don't let it go long — a defensive, stall-and-heal team loses to a stacking engine by design.",),
    ),
    Threat(
        "speed_race",
        "Speed is earned during the fight, not brought to it",
        (
            r"all characters have -\d+ Speed",
            r"-\d+ Speed;.{0,120}gain \d+ Speed",
            r"critical hit, gain \d+ Speed",
            r"gain \d+ Speed \(max",
        ),
        "Everyone is slowed by a flat amount and buys speed back by meeting the rule (usually "
        "landing crits). A flat penalty doesn't level the field — it widens it: subtracting 100 "
        "from 350 and from 200 leaves the fast unit taking 2.5x the turns instead of 1.75x. "
        "Whoever is fastest moves first, crits first, and accelerates away.",
        # You have to win the race, not survive it: crit denial starves them, crit
        # chance and turn-meter gain feed you, and speed is the entry fee.
        use=("crit_chance", "tm_gain", "crit_avoidance", "tm_removal", "daze"),
        avoid=(
            "Don't bring your slow units — a flat speed penalty magnifies speed gaps rather than closing them, "
            "and the fastest side can take a full round before you move at all.",
            "Don't bring low-crit-chance units; they never earn their speed back and end up taking one turn to the enemy's three.",
        ),
    ),
    Threat(
        "counter_attack",
        "Counters and retaliates when attacked",
        (r"counter chance", r"\bcounter[s]? attack", r"chance to counter"),
        "Attacking into them gives them extra attacks, so the more times you swing, the more they "
        "hit back.",
        use=("stun", "ability_block", "daze", "instant_defeat"),
        avoid=("Don't spam multi-hit basics into a counter-heavy team — you're handing them free turns.",),
    ),
    Threat(
        "turn_meter_gain",
        "Gains bonus Turn Meter",
        (r"gain[s]? \d+% Turn Meter", r"bonus Turn Meter"),
        "They take extra turns, which accelerates every other part of their kit.",
        use=("daze", "tm_removal", "stun"),
        avoid=("Don't count on winning the speed race outright — they're generating turns, not just starting faster.",),
    ),
    Threat(
        "assist_chain",
        "Calls assists",
        (
            r"call[s]?[^.]{0,40}to assist",
            r"assist[s]?\b[^.]{0,80}dealing",
            r"chance to assist",
            r"assist when",
        ),
        "One enemy turn becomes several attacks, multiplying damage and on-hit triggers.",
        use=("daze", "stun", "ability_block", "taunt"),
        avoid=(),
    ),
    Threat(
        "taunt_wall",
        "Taunts to protect the real threat",
        (r"\bTaunt\b",),
        "You're being funnelled into the wrong target while the dangerous unit works freely.",
        use=("dispel", "ability_block", "instant_defeat"),
        avoid=("Don't burn your damage into the taunting tank if the engine is behind it.",),
    ),
    Threat(
        "unresistable",
        "Effects that can't be resisted",
        (r"can'?t be resisted",),
        "Tenacity does nothing here — this lands regardless of your stats.",
        use=("cleanse", "foresight", "instant_defeat"),
        avoid=("Don't mod for Tenacity expecting to dodge this; it's explicitly unresistable.",),
    ),
    Threat(
        "undispellable",
        "Buffs that can't be dispelled",
        (r"can'?t be (?:copied, )?dispelled", r"can'?t be dispelled or prevented"),
        "You can't strip this one off, so plan around it rather than through it.",
        use=("buff_prevention", "instant_defeat", "tm_removal"),
        avoid=("Don't build the plan around a dispeller — this specific effect is immune to it.",),
    ),
    Threat(
        "damage_reflect",
        "Reflects damage back at you (Retribution)",
        (
            r"deal[s]? true damage to that enemy equal to",
            r"\bRetribution\b",
            r"receives? damage from an enemy, they deal",
        ),
        "Hitting them hurts you, and it scales with the *number* of hits — so assist chains and "
        "multi-hit attackers punish themselves.",
        use=("heal", "protection_up", "instant_defeat", "foresight"),
        avoid=(
            "Don't bring assist-callers or multi-hit attackers — every individual hit reflects back at you.",
            "Don't grind it out with chip damage; land fewer, bigger hits instead.",
        ),
    ),
    Threat(
        "true_damage",
        "Deals true damage",
        (r"\btrue damage\b",),
        "True damage ignores Defense and mitigation, so tanking it with Defense stats won't help — "
        "raw health, healing and avoidance will.",
        use=("heal", "protection_up", "foresight"),
        avoid=("Don't rely on Defense Up or armour stacking; true damage goes straight through it.",),
    ),
    Threat(
        "enemy_instant_defeat",
        "Can instantly defeat your units",
        (r"instantly defeat",),
        "Health totals won't save the targeted unit — positioning and prevention will.",
        use=("taunt", "foresight", "protection_up", "tm_removal"),
        avoid=(),
    ),
)


@dataclass
class ToolBearer:
    """One of your units that brings a given tool, and the line that proves it."""

    base_id: str
    unit_name: str
    ability_name: str
    ability_kind: str
    quote: str
    stars: int
    gear_level: int
    relic_level: int
    needs_zeta: bool = False
    needs_omicron: bool = False

    @property
    def readiness(self) -> int:
        """Rough fieldability score — a counter you can't field doesn't count."""
        return self.relic_level * 100 + self.gear_level * 5 + self.stars


@dataclass
class ToolAdvice:
    key: str
    label: str
    blurb: str
    bearers: list[ToolBearer] = field(default_factory=list)
    extra: int = 0  # bearers beyond MAX_BEARERS

    @property
    def have(self) -> bool:
        return bool(self.bearers)


@dataclass
class CounterStep:
    key: str
    label: str
    quote: str  # the enemy sentence that triggered this
    means: str
    tools: list[ToolAdvice] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)


@dataclass
class CounterReport:
    player_name: str
    ally_code: str
    source_label: str
    threat_text: str
    steps: list[CounterStep] = field(default_factory=list)
    trial_number: int | None = None
    tips: list[str] = field(default_factory=list)
    query: str = ""  # free-text ability search
    matches: list[ToolBearer] = field(default_factory=list)
    squads: list = field(default_factory=list)  # list[CounterSquad]
    min_relic: int = 0
    modifiers: list[dict] = field(default_factory=list)  # name/scope/text per modifier
    donors: list = field(default_factory=list)  # list[ModDonor] — speed mods to move
    speed_matters: bool = False  # a speed-race modifier is in play

    @property
    def analysed(self) -> bool:
        return bool(self.threat_text)

    @property
    def avoid_all(self) -> list[str]:
        """Every backfire warning across the plan, de-duplicated, order preserved."""
        seen: dict[str, None] = {}
        for step in self.steps:
            for line in step.avoid:
                seen.setdefault(line, None)
        return list(seen)


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _trim(sentence: str, pattern: str) -> str:
    """Keep a quote readable, centred on the phrase that matched."""
    if len(sentence) <= MAX_QUOTE:
        return sentence
    m = re.search(pattern, sentence, re.IGNORECASE)
    start = max(0, (m.start() if m else 0) - MAX_QUOTE // 3)
    excerpt = sentence[start : start + MAX_QUOTE]
    # Don't start or end mid-word — a clipped word reads like a typo.
    if start and " " in excerpt:
        excerpt = excerpt.split(" ", 1)[1]
    if start + MAX_QUOTE < len(sentence) and " " in excerpt:
        excerpt = excerpt.rsplit(" ", 1)[0]
    return ("…" if start else "") + excerpt.strip() + "…"


def _find(
    patterns: tuple[str, ...],
    sentences: list[str],
    excludes: tuple[str, ...] = (),
) -> str | None:
    """First sentence matching any pattern — the evidence for a match.

    A sentence matching `excludes` is skipped: the wording matches but points at
    the wrong target (an ally, or the unit itself).
    """
    for sentence in sentences:
        if excludes and any(re.search(x, sentence, re.IGNORECASE) for x in excludes):
            continue
        for pattern in patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                return _trim(sentence, pattern)
    return None


def _learned_flags(unit_skills: dict[str, int], ability: dict) -> tuple[bool, bool]:
    """(needs_zeta, needs_omicron) for an ability, from live skill tiers.

    Ability text is max-tier wording, so an effect can read as active when its
    zeta isn't learned yet. Only abilities we have definitions for can be judged;
    anything unknown is reported as learned rather than warned about falsely.
    """
    defn = ability_defs().get(ability.get("i", ""))
    if not defn:
        return False, False
    raw = unit_skills.get(ability["i"])
    if raw is None:
        return False, False
    tier = raw + COMLINK_TIER_OFFSET
    needs_zeta = bool(defn.get("z")) and not is_zeta_learned(defn, tier)
    needs_omicron = bool(defn.get("o")) and not is_omicron_learned(defn, tier)
    return needs_zeta, needs_omicron


def _roster_abilities(player: Player):
    """Every character ability on the roster, paired with its unit."""
    for unit in player.units:
        if is_ship(unit.base_id):
            continue
        for ability in abilities_of(unit.base_id):
            yield unit, ability


def find_tool_bearers(player: Player, tool: Tool) -> list[ToolBearer]:
    """Units whose abilities provide `tool`, best-equipped first."""
    bearers: list[ToolBearer] = []
    for unit, ability in _roster_abilities(player):
        quote = _find(tool.patterns, _sentences(ability["d"]), tool.excludes)
        if not quote:
            continue
        needs_zeta, needs_omicron = _learned_flags(unit.skills, ability)
        bearers.append(
            ToolBearer(
                base_id=unit.base_id,
                unit_name=display_name(unit.base_id),
                ability_name=ability["n"],
                ability_kind=ability["k"],
                quote=quote,
                stars=unit.stars,
                gear_level=unit.gear_level,
                relic_level=unit.relic_level,
                needs_zeta=needs_zeta,
                needs_omicron=needs_omicron,
            )
        )
    # Prefer units you can actually field, and a learned counter over a locked one.
    bearers.sort(key=lambda b: (not (b.needs_zeta or b.needs_omicron), b.readiness), reverse=True)
    # One row per unit: a kit that provides the same tool on two abilities would
    # otherwise take two of the listed slots and read like a duplicate.
    best: dict[str, ToolBearer] = {}
    for b in bearers:
        best.setdefault(b.base_id, b)
    return list(best.values())


def search_abilities(player: Player, query: str) -> list[ToolBearer]:
    """Free-text search across your roster's ability descriptions."""
    query = query.strip()
    if not query:
        return []
    pattern = re.escape(query)
    results: list[ToolBearer] = []
    for unit, ability in _roster_abilities(player):
        quote = _find((pattern,), _sentences(ability["d"]))
        if not quote:
            continue
        needs_zeta, needs_omicron = _learned_flags(unit.skills, ability)
        results.append(
            ToolBearer(
                base_id=unit.base_id,
                unit_name=display_name(unit.base_id),
                ability_name=ability["n"],
                ability_kind=ability["k"],
                quote=quote,
                stars=unit.stars,
                gear_level=unit.gear_level,
                relic_level=unit.relic_level,
                needs_zeta=needs_zeta,
                needs_omicron=needs_omicron,
            )
        )
    results.sort(key=lambda b: b.readiness, reverse=True)
    return results


def detect_threats(text: str) -> list[tuple[Threat, str]]:
    """Threats present in enemy text, each with the sentence that revealed it."""
    sentences = _sentences(text)
    found: list[tuple[Threat, str]] = []
    for threat in THREATS:
        quote = _find(threat.patterns, sentences)
        if quote:
            found.append((threat, quote))
    return found


def analyze_counters(
    player: Player,
    threat_text: str = "",
    trial_number: int | None = None,
    query: str = "",
) -> CounterReport:
    """Build a counter plan for pasted enemy text or a Conquest trial."""
    source_label = "Pasted enemy text"
    tips: list[str] = []
    min_relic = 0
    modifiers: list[dict] = []
    if trial_number is not None:
        t = trial(trial_number)
        if t is None:
            raise ValueError(f"Unknown Conquest trial {trial_number}.")
        threat_text = modifier_text(t)
        source_label = trial_label(t)
        tips = list(t.get("tips", []))
        min_relic = int(t.get("min_relic") or 0)
        modifiers = modifier_entries(t)

    report = CounterReport(
        player_name=player.name,
        ally_code=player.ally_code,
        source_label=source_label,
        threat_text=threat_text.strip(),
        trial_number=trial_number,
        tips=tips,
        query=query.strip(),
        min_relic=min_relic,
        modifiers=modifiers,
    )
    if report.query:
        report.matches = search_abilities(player, report.query)
    if not report.threat_text:
        return report

    # Tool lookups are the expensive part, so resolve each tool at most once.
    cache: dict[str, ToolAdvice] = {}

    def advice(key: str) -> ToolAdvice | None:
        tool = TOOLS_BY_KEY.get(key)
        if tool is None:
            return None
        if key not in cache:
            bearers = find_tool_bearers(player, tool)
            cache[key] = ToolAdvice(
                key=tool.key,
                label=tool.label,
                blurb=tool.blurb,
                bearers=bearers[:MAX_BEARERS],
                extra=max(0, len(bearers) - MAX_BEARERS),
            )
        return cache[key]

    for threat, quote in detect_threats(report.threat_text):
        tools = [a for a in (advice(k) for k in threat.use) if a is not None]
        report.steps.append(
            CounterStep(
                key=threat.key,
                label=threat.label,
                quote=quote,
                means=threat.means,
                tools=tools,
                avoid=list(threat.avoid),
            )
        )

    # Assemble squads from the tools the detected threats actually call for,
    # ordered so the most-wanted tool leads.
    from .counter_squads import build_counter_squads, find_mod_donors

    wanted: dict[str, int] = {}
    for threat, _ in detect_threats(report.threat_text):
        for key in threat.use:
            wanted[key] = wanted.get(key, 0) + 1
    ranked = [k for k, _ in sorted(wanted.items(), key=lambda kv: kv[1], reverse=True)]
    threat_keys = {s.key for s in report.steps}
    report.squads = build_counter_squads(
        player, ranked, threat_keys=threat_keys, min_relic=report.min_relic
    )

    # When turn order decides the fight, moving Speed mods off the bench is
    # faster than farming, so surface the best donors for the top squad.
    report.speed_matters = "speed_race" in threat_keys
    if report.speed_matters and report.squads:
        squad_ids = {m.base_id for m in report.squads[0].members}
        report.donors = find_mod_donors(player, squad_ids)
    return report
