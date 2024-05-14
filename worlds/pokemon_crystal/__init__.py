import settings
from typing import List, Union, ClassVar, Dict, Any, Tuple
import copy
import logging

from BaseClasses import Tutorial
from worlds.AutoWorld import World, WebWorld
from .client import PokemonCrystalClient
from .options import PokemonCrystalOptions
from .regions import create_regions
from .items import PokemonCrystalItem, create_item_label_to_code_map, get_item_classification
from .rules import set_rules
from .data import (PokemonData, MoveData, TrainerData, LearnsetData, data as crystal_data, BASE_OFFSET)
from .rom import generate_output
from .locations import create_locations, PokemonCrystalLocation, create_location_label_to_id_map
from .utils import get_random_pokemon, get_random_filler_item, get_random_held_item, get_random_types, get_type_colors, \
    get_random_colors, get_random_base_stats, get_tmhm_compatibility


class PokemonCrystalSettings(settings.Group):
    class RomFile(settings.UserFilePath):
        description = "Pokemon Crystal (UE) (V1.0) ROM File"
        copy_to = "Pokemon - Crystal Version (UE) (V1.0) [C][!].gbc"
        md5s = ["9f2922b235a5eeb78d65594e82ef5dde"]

    class RomStart(str):
        """
        Set this to false to never autostart a rom (such as after patching)
        True for operating system default program
        Alternatively, a path to a program to open the .gb file with
        """

    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: Union[RomStart, bool] = True


class PokemonCrystalWebWorld(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Pokemon Crystal with Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["AliceMousie"]
    )]


class PokemonCrystalWorld(World):
    """the only good pokemon game"""
    game = "Pokemon Crystal"

    topology_present = True
    web = PokemonCrystalWebWorld()

    settings_key = "pokemon_crystal_settings"
    settings: ClassVar[PokemonCrystalSettings]

    options_dataclass = PokemonCrystalOptions
    options: PokemonCrystalOptions

    data_version = 0
    required_client_version = (0, 4, 4)

    item_name_to_id = create_item_label_to_code_map()
    location_name_to_id = create_location_label_to_id_map()
    item_name_groups = {}  # item_groups

    generated_pokemon: Dict[str, PokemonData]
    generated_starters: Tuple[List[str], List[str], List[str]]
    generated_trainers: Dict[str, TrainerData]
    generated_palettes: Dict[str, List[List[int]]]

    def generate_early(self) -> None:
        if self.options.johto_only:
            if self.options.goal.value == 1:
                self.options.goal.value = 0
                logging.warning(
                    "Pokemon Crystal: Red goal is incompatible with Johto Only. "
                    "Changing goal to Elite Four for player %s.",
                    self.multiworld.get_player_name(self.player))
            if self.options.elite_four_badges.value > 8:
                self.options.elite_four_badges.value = 8
                logging.warning(
                    "Pokemon Crystal: Elite Four Badges >8 incompatible with Johto Only. "
                    "Changing Elite Four Badges to 8 for player %s.",
                    self.multiworld.get_player_name(self.player))

    def create_regions(self) -> None:
        regions = create_regions(self)
        create_locations(self, regions)
        self.multiworld.regions.extend(regions.values())

    def create_items(self) -> None:
        item_locations: List[PokemonCrystalLocation] = [
            location
            for location in self.multiworld.get_locations(self.player)
            if location.address is not None
        ]

        default_itempool = [self.create_item_by_code(
            location.default_item_code if location.default_item_code > BASE_OFFSET
            else get_random_filler_item(self.random))
            for location in item_locations]
        self.multiworld.itempool += default_itempool

    def set_rules(self) -> None:
        set_rules(self)

    def generate_output(self, output_directory: str) -> None:
        def get_random_move(type=None):
            if type is None:
                move_pool = [move_name for move_name, move_data in crystal_data.moves.items() if
                             move_data.id > 0 and not move_data.is_hm and move_name not in ["STRUGGLE", "BEAT_UP"]]
            else:
                move_pool = [move_name for move_name, move_data in crystal_data.moves.items() if
                             move_data.id > 0 and not move_data.is_hm and move_data.type == type and move_name not in [
                                 "STRUGGLE", "BEAT_UP"]]
            return self.random.choice(move_pool)

        def get_random_move_from_learnset(pokemon, level):
            move_pool = [move.move for move in crystal_data.pokemon[pokemon].learnset if
                         move.level <= level and move.move != "NO_MOVE"]
            return self.random.choice(move_pool)

        def set_rival_fight(trainer_name, trainer, new_pokemon):
            trainer.pokemon[-1][1] = new_pokemon
            self.generated_trainers[trainer_name] = trainer

        self.generated_pokemon = copy.deepcopy(crystal_data.pokemon)
        self.generated_starters = (["CYNDAQUIL", "QUILAVA", "TYPHLOSION"],
                                   ["TOTODILE", "CROCONAW", "FERALIGATR"],
                                   ["CHIKORITA", "BAYLEEF", "MEGANIUM"])
        self.generated_trainers = copy.deepcopy(crystal_data.trainers)
        self.generated_palettes = {}

        if self.options.randomize_types.value > 0:
            for pkmn_name, pkmn_data in self.generated_pokemon.items():
                new_types = get_random_types(self.random)
                pkmn_list = [pkmn_name]
                if self.options.randomize_types.value == 1:
                    if not pkmn_data.is_base:
                        continue
                    for evo in pkmn_data.evolutions:
                        pkmn_list.append(evo[-1])
                        evo_poke = crystal_data.pokemon[evo[-1]]
                        for second_evo in evo_poke.evolutions:
                            pkmn_list.append(second_evo[-1])
                for poke in pkmn_list:
                    self.generated_pokemon[poke] = self.generated_pokemon[poke]._replace(types=new_types)

        if self.options.randomize_palettes.value > 0:
            for pkmn_name, pkmn_data in self.generated_pokemon.items():
                pals = []
                if self.options.randomize_palettes.value == 1:
                    pals.append(get_type_colors(pkmn_data.types, self.random))
                else:
                    pals.append(get_random_colors(self.random))
                pals.append(get_random_colors(self.random))  # shiny palette
                self.generated_palettes[pkmn_name] = pals

        if self.options.randomize_base_stats.value > 0:
            for pkmn_name, pkmn_data in self.generated_pokemon.items():
                if self.options.randomize_base_stats.value == 1:
                    new_base_stats = get_random_base_stats(self.random, pkmn_data.bst)
                else:
                    new_base_stats = get_random_base_stats(self.random)
                self.generated_pokemon[pkmn_name] = self.generated_pokemon[pkmn_name]._replace(
                    base_stats=new_base_stats)

        if self.options.randomize_learnsets:
            for pkmn_name, pkmn_data in self.generated_pokemon.items():
                learn_levels = [1 for move in pkmn_data.learnset if move.move ==
                                "NO_MOVE" and self.options.randomize_learnsets > 1]
                for move in pkmn_data.learnset:
                    if move.move != "NO_MOVE":
                        learn_levels.append(move.level)
                new_learnset = [LearnsetData(level, get_random_move()) for level in learn_levels]
                self.generated_pokemon[pkmn_name] = self.generated_pokemon[pkmn_name]._replace(learnset=new_learnset)

        if self.options.tm_compatibility > 0 or self.options.hm_compatibility > 0:
            for pkmn_name, pkmn_data in self.generated_pokemon.items():
                new_tmhms = get_tmhm_compatibility(self.options.tm_compatibility.value,
                                                   self.options.hm_compatibility.value, pkmn_data.types, self.random)
                self.generated_pokemon[pkmn_name] = self.generated_pokemon[pkmn_name]._replace(tm_hm=new_tmhms)

        if self.options.randomize_starters:
            for evo_line in self.generated_starters:
                rival_fights = [(trainer_name, trainer) for trainer_name, trainer in self.generated_trainers.items() if
                                trainer_name.startswith("RIVAL_" + evo_line[0])]

                evo_line[0] = get_random_pokemon(self.random)
                for trainer_name, trainer in rival_fights:
                    set_rival_fight(trainer_name, trainer, evo_line[0])

                rival_fights = [(trainer_name, trainer) for trainer_name, trainer in self.generated_trainers.items() if
                                trainer_name.startswith("RIVAL_" + evo_line[1])]

                first_evolutions = crystal_data.pokemon[evo_line[0]].evolutions
                evo_line[1] = self.random.choice(first_evolutions)[-1] if len(first_evolutions) else evo_line[0]
                for trainer_name, trainer in rival_fights:
                    set_rival_fight(trainer_name, trainer, evo_line[1])

                rival_fights = [(trainer_name, trainer) for trainer_name, trainer in self.generated_trainers.items() if
                                trainer_name.startswith("RIVAL_" + evo_line[2])]

                second_evolutions = crystal_data.pokemon[evo_line[1]].evolutions
                evo_line[2] = self.random.choice(second_evolutions)[-1] if len(
                    second_evolutions) else evo_line[1]
                for trainer_name, trainer in rival_fights:
                    set_rival_fight(trainer_name, trainer, evo_line[2])

        if self.options.randomize_trainer_parties:
            for trainer_name, trainer_data in self.generated_trainers.items():
                new_party = trainer_data.pokemon
                for i, pokemon in enumerate(trainer_data.pokemon):
                    new_pkmn_data = pokemon
                    if not trainer_name.startswith("RIVAL") or i != len(trainer_data.pokemon) - 1:
                        match_types = [None, None]
                        if self.options.randomize_trainer_parties == 1:
                            match_types = crystal_data.pokemon[new_pkmn_data[1]].types
                        new_pokemon = get_random_pokemon(self.random, match_types)
                        new_pkmn_data[1] = new_pokemon
                    if trainer_data.trainer_type in ["TRAINERTYPE_ITEM", "TRAINERTYPE_ITEM_MOVES"]:
                        new_pkmn_data[2] = get_random_held_item(self.random)
                    if trainer_data.trainer_type not in ["TRAINERTYPE_MOVES", "TRAINERTYPE_ITEM_MOVES"]:
                        continue
                    move_offset = 2 if trainer_data.trainer_type == "TRAINERTYPE_MOVES" else 3
                    while move_offset < len(new_pkmn_data) and new_pkmn_data[move_offset] != "NO_MOVE":
                        new_pkmn_data[move_offset] = get_random_move_from_learnset(
                            new_pkmn_data[1], int(new_pkmn_data[0]))
                        move_offset += 1
                    new_party[i] = new_pkmn_data
                self.generated_trainers[trainer_name] = self.generated_trainers[trainer_name]._replace(
                    pokemon=new_party)

        generate_output(self, output_directory)

    def fill_slot_data(self) -> Dict[str, Any]:
        slot_data = self.options.as_dict(
            "randomize_hidden_items",
            "randomize_starters",
            "randomize_wilds",
            "randomize_learnsets",
            "blind_trainers",
            "better_marts",
            "goal",
            "require_itemfinder"
        )
        return slot_data

    def write_spoiler(self, spoiler_handle) -> None:
        if self.options.randomize_starters:
            spoiler_handle.write(f"\n\nStarter Pokemon ({self.multiworld.player_name[self.player]}):\n\n")
            for evo in self.generated_starters:
                spoiler_handle.write(f"{evo[0]} -> {evo[1]} -> {evo[2]}\n")

    def create_item(self, name: str) -> PokemonCrystalItem:
        return self.create_item_by_code(self.item_name_to_id[name])

    def create_item_by_code(self, item_code: int) -> PokemonCrystalItem:
        return PokemonCrystalItem(
            self.item_id_to_name[item_code],
            get_item_classification(item_code),
            item_code,
            self.player
        )
