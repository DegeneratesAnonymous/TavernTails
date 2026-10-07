"""Genre-specific starter-seed pools for Quick Start campaigns.

The generic pools in ``content_bundles`` read as a border-village mystery, so a
Fantasy, Horror or Sci-Fi Quick Start (a genre and a title, nothing else) came
out as witnesses and road wardens whatever was chosen. These pools replace them
when the campaign explicitly names one of these genres.

Each place is a small coherent scenario: its own name suffix, NPC roles, stakes,
player decision, and the events and open questions that belong to it, so a
druid grove never gets a question about a space station. Events complete
"A <place> where <event>." and are lower-case. Mystery keeps the generic pools.
"""
from __future__ import annotations

from typing import NamedTuple


class Place(NamedTuple):
    type: str
    suffix: str
    roles: tuple[str, ...]
    stakes: str
    decision: str
    events: tuple[str, ...]
    questions: tuple[str, ...]


class GenreSeeds(NamedTuple):
    places: tuple[Place, ...]

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(e for p in self.places for e in p.events)

    @property
    def questions(self) -> tuple[str, ...]:
        return tuple(q for p in self.places for q in p.questions)


GENRE_SEEDS: dict[str, GenreSeeds] = {
    "fantasy": GenreSeeds(places=(
        Place("ruined wizard's tower", "Tower", ("Hedge-Wizard", "Apprentice Archivist", "Tower Caretaker"),
              "The wards finish unraveling at moonrise, and whatever they held back will be loose.",
              "Reinforce the wards before moonrise, or learn what the tower was built to contain.",
              ("a ward that held for generations flickers out", "a sealed grimoire turns its own pages"),
              ("Who broke the ward, and why now?", "What was this tower built to keep in?")),
        Place("druid grove at the forest's edge", "Grove", ("Grove-Keeper", "Hunter", "Wandering Druid"),
              "The grove's heartwood is dying, and the creatures it sheltered are leaving the wood.",
              "Tend the grove, or follow the fleeing creatures to learn what drove them out.",
              ("the oldest tree weeps black sap", "every beast in the wood walks out at once"),
              ("What is poisoning the heartwood?", "What are the animals running from?")),
        Place("hill town below a barrow", "Barrow", ("Barrow-Warden", "Town Reeve", "Gravetender"),
              "The barrow door stands open, and the town has until dawn to decide who goes in.",
              "Enter the barrow, or hold the town together while others do.",
              ("the barrow door swings open on its own", "a king's name is carved fresh on the lintel"),
              ("Who opened the barrow?", "What was buried here, and who is it for?")),
        Place("temple of the old gods", "Temple", ("Temple Oracle", "Acolyte", "Stonemason"),
              "The oracle's last prophecy names someone present, and the order wants it buried.",
              "Hear the prophecy, or help the oracle hide it.",
              ("a prophecy is read aloud and no one agrees whom it names", "the altar relic stirs for the first time in a century"),
              ("What does the prophecy really name?", "Why did the relic wake now?")),
        Place("mine that something now haunts", "Delve", ("Foreman", "Dwarven Surveyor", "Lone Survivor"),
              "Something below is hunting the shift that went down, and the lamps are running low.",
              "Descend after the missing shift, or seal the shaft and answer for it.",
              ("the night shift fails to come up", "the walls hum with a voice no one will repeat"),
              ("What woke the thing below?", "Who sealed the lower gallery, and when?")),
    )),
    "horror": GenreSeeds(places=(
        Place("fog-bound fishing village", "Cove", ("Harbor Warden", "Net-Mender", "Lighthouse Keeper"),
              "The tide has begun returning more than it took, and by morning no one will open their doors.",
              "Watch the shore through the night, or follow what walked out of the water.",
              ("the tide brings back the boats that were lost", "every net comes up full of the same pale shells"),
              ("What came back with the tide?", "Who is the lighthouse still signaling?")),
        Place("abandoned asylum", "Asylum", ("Night Orderly", "Last Patient", "Groundskeeper"),
              "The doors lock at dusk, and what was kept inside has started answering the knocking.",
              "Search the wards before dark, or leave and let the town find out.",
              ("a bell rings in a ward that was bricked up", "the patients' records rewrite themselves"),
              ("What is behind the bricked-up ward?", "Who is writing in the records?")),
        Place("chapel beside a fresh grave", "Chapel", ("Sexton", "Parish Clerk", "Grieving Widow"),
              "The grave was dug for someone not yet dead, and the ground has begun to settle.",
              "Open the grave, or keep watch over the person it was dug for.",
              ("someone returns who was buried last winter", "a grave is dug in the night with no name on it"),
              ("Who is the grave meant for?", "What walked out of the churchyard?")),
        Place("farmhouse at the end of a dead road", "Farm", ("Farmer's Daughter", "Hired Hand", "Neighbor"),
              "The family has not been seen since dusk, and the lamps in every window are lit.",
              "Go in through the front door, or learn why the neighbors will not.",
              ("the dogs refuse to cross the threshold", "a child describes a visitor no one else can see"),
              ("Who is the child talking to?", "Why will the animals not go near the house?")),
        Place("winter camp of a traveling fair", "Fairground", ("Ringmaster", "Fortune-Teller", "Stagehand"),
              "One tent has been sealed from the inside, and the performers refuse to say who is in it.",
              "Cut the tent open, or find out who agreed to keep it shut.",
              ("a mirror shows the tent as it was before the fire", "the music box plays when no one winds it"),
              ("Who is in the sealed tent?", "What happened in this camp before the fire?")),
    )),
    "sci-fi": GenreSeeds(places=(
        Place("derelict relay station", "Relay", ("Station Engineer", "Comms Officer", "Stowaway"),
              "Life support cycles down in six hours, and the only repair crew is whoever is aboard.",
              "Restore the relay's power, or cut loose before whatever called it arrives.",
              ("a distress beacon repeats from a ship that was never launched", "the station AI answers questions no one asked"),
              ("Who sent the beacon?", "What is the station AI protecting?")),
        Place("orbital habitat ring", "Ring", ("Habitat Warden", "Hydroponics Lead", "Dock Inspector"),
              "The ring's spin is drifting, and the council is hiding the readings.",
              "Publish the readings, or fix the spin quietly and risk being too late.",
              ("every clock on the ring disagrees by exactly nine minutes", "the spin readings are quietly deleted each night"),
              ("Why do the clocks disagree by nine minutes?", "Who is deleting the readings?")),
        Place("frontier colony landing site", "Landing", ("Colony Administrator", "Survey Pilot", "Medic"),
              "The resupply window closes in three days, and the colony's count of survivors is wrong.",
              "Correct the count and ask for help, or protect the colony's story until the ship lands.",
              ("a signal arrives from the colony before it was founded", "the survivor count is one higher every morning"),
              ("Who is the extra survivor?", "What is the signal from before the colony?")),
        Place("survey ship adrift", "Drifter", ("First Officer", "Systems Technician", "Sole Passenger"),
              "The reactor holds for one more jump, and half the crew wants to take it elsewhere.",
              "Take the jump home, or follow the signal that brought the ship here.",
              ("a crewmate's logs show them working while they slept", "a sealed cargo container starts to hum"),
              ("Who is in the logs while the crew sleeps?", "What is inside the container?")),
        Place("research dome on an ice moon", "Dome", ("Lead Researcher", "Dome Technician", "Security Chief"),
              "The drill team stopped answering at shift change, and the dome seals itself at nightfall.",
              "Go below after the drill team, or lock the dome and wait for the relief flight.",
              ("the drill team stops answering mid-sentence", "the ice below the dome begins to ping back"),
              ("What did the drill team hit?", "What is answering from under the ice?")),
    )),
    "political": GenreSeeds(places=(
        Place("council chamber on the eve of a vote", "Chamber", ("Senior Clerk", "Guild Factor", "Envoy"),
              "The vote closes at dusk, and the winners will rewrite who may speak at the next one.",
              "Win the vote, or expose how it was fixed.",
              ("a signet appears in a rival's hand", "two ballots are found with the same hand-written name"),
              ("Who gains if the vote fails?", "Who forged the ballots?")),
        Place("royal court during a succession dispute", "Court", ("Chamberlain", "Court Herald", "Rival Heir"),
              "The regent will name an heir before the court disperses, and two houses have already armed.",
              "Back a claimant, or force the regent to wait.",
              ("an heir is named in a will that has not been read", "a succession clause is quoted that no one remembers writing"),
              ("Who wrote the will?", "Who forged the clause?")),
        Place("trade guild hall", "Hall", ("Guildmaster", "Ledger-Keeper", "Charter Lawyer"),
              "The charter renewal is tomorrow, and the ledgers do not match the oaths sworn over them.",
              "Find the missing entries, or let the renewal pass and answer for it.",
              ("a ledger of bribes surfaces during the oath", "a page is cut from the charter book overnight"),
              ("Who is paying whom?", "What did the missing page say?")),
        Place("border treaty pavilion", "Pavilion", ("Treaty Envoy", "Border Marshal", "Interpreter"),
              "The ceasefire ends at midnight, and each side believes the other has already broken it.",
              "Carry proof between the camps, or keep the talks from breaking down.",
              ("a trusted envoy defects overnight", "a courier is caught carrying both sides' terms"),
              ("Why did the envoy leave?", "Who benefits if the talks fail?")),
        Place("city archive under guard", "Archive", ("Archivist", "Records Warden", "Petitioner"),
              "A sealed record is due to be read aloud tomorrow, and someone is trying to alter it tonight.",
              "Protect the record, or read it first.",
              ("the seal on the record is found already broken", "two houses accept the same marriage offer in the register"),
              ("Who has been in the archive at night?", "Which house blinks first?")),
    )),
    "survival": GenreSeeds(places=(
        Place("last well on a salt flat", "Well", ("Water-Keeper", "Scout", "Caravan Master"),
              "The well gives one more day of water, and everyone at it knows the count.",
              "Ration and wait for the caravan, or gamble on the crossing.",
              ("the last of the clean water turns bitter", "a scout returns alone and will not say why"),
              ("What is wrong with the water?", "Where did the scout's companions go?")),
        Place("lifeboat camp after the wreck", "Shore", ("Ship's Mate", "Surgeon", "Passenger"),
              "The tide takes the supply cache by dawn, and the rescue lamp has not been answered.",
              "Haul the cache above the tide line, or send someone to climb for a signal.",
              ("the signal fire goes out with no one on watch", "someone is found carrying more than their share"),
              ("Who let the fire go out?", "Who is hoarding supplies?")),
        Place("burned-out supply depot", "Depot", ("Quartermaster", "Scavenger", "Refugee"),
              "What the fire spared will not feed everyone, and a second group is on the road to it.",
              "Share the stores and hold the depot, or take what you can carry and go.",
              ("a stranger offers food in exchange for a name", "a second group is seen on the ridge at dawn"),
              ("What does the stranger want in return?", "Who else knows about the stores?")),
        Place("mountain hut before the pass closes", "Hut", ("Hut Warden", "Guide", "Stranded Climber"),
              "The storm will close the pass within the hour, and the hut has fuel for two nights.",
              "Cross before the pass closes, or dig in and trust the fuel.",
              ("the storm shifts and closes the only trail", "a climber arrives without the rest of the rope team"),
              ("How long will the pass stay shut?", "What happened to the rest of the rope team?")),
        Place("flooded lowland refuge", "Refuge", ("Refuge Elder", "Boatman", "Midwife"),
              "The water is rising a hand an hour, and the boats can carry only half of the camp.",
              "Decide who crosses first, or search for higher ground on foot.",
              ("a boat is found cut loose in the night", "the water rises faster than the markers say"),
              ("Who cut the boat loose?", "How much time is really left?")),
    )),
}


def pools_for(genre: str) -> GenreSeeds | None:
    """The genre's pools, or None for mystery, unknown, or unspecified genres."""
    return GENRE_SEEDS.get(str(genre or "").strip().lower())
