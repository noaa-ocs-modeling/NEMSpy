from datetime import timedelta
from enum import Enum
import os
from os import PathLike
from textwrap import indent
from typing import Iterator, Tuple

from .model.base import ConfigurationEntry, Connection, INDENTATION, Model, \
    ModelType, ModelVerbosity, RemapMethod
from .utilities import get_logger

LOGGER = get_logger('configuration')


class Earth(ConfigurationEntry):
    """
    multi-model coupling container
    """

    entry_type = 'EARTH'

    def __init__(self, verbosity: ModelVerbosity = None, **kwargs):
        if verbosity is None:
            verbosity = ModelVerbosity.MINIMUM

        self.__models = {model_type: None for model_type in ModelType}

        self.attributes = {}
        for key, value in kwargs.items():
            key = key.upper()
            if key in {entry.name for entry in ModelType}:
                if isinstance(value, Model):
                    self[ModelType[key]] = value
            else:
                self.attributes[key] = value

        self.attributes['Verbosity'] = verbosity

    @property
    def models(self):
        return self.__models

    def __getitem__(self, model_type: ModelType) -> Model:
        return self.__models[model_type]

    def __setitem__(self, model_type: ModelType, model: Model):
        assert model_type == model.type
        if self.__models[model_type] is not None:
            LOGGER.warning(f'overwriting existing "{model_type.name}" model: '
                           f'{repr(self[model_type])}')
        self.__models[model_type] = model

    def __contains__(self, model_type: ModelType):
        return model_type in self.__models

    def __iter__(self) -> Iterator[Tuple[ModelType, Model]]:
        for model_type, model in self.models.items():
            yield model_type, model

    def __str__(self) -> str:
        attributes = [
            f'{attribute} = {value if not isinstance(value, Enum) else value.value}'
            for attribute, value in self.attributes.items()
        ]

        return '\n'.join([
            f'{self.entry_type}_component_list: {" ".join(model_type.value for model_type, model in self.models.items() if model is not None)}',
            f'{self.entry_type}_attributes::',
            indent('\n'.join(attributes), INDENTATION),
            '::'
        ])

    def __repr__(self) -> str:
        kwargs = [f'{model_type.name}={repr(model)}'
                  for model_type, model in self.models.items()] + \
                 [f'{key}={value}'
                  for key, value in self.attributes.items()]
        return f'{self.__class__.__name__}({self.attributes["Verbosity"]}, {", ".join(kwargs)})'


class ModelSequence(ConfigurationEntry):
    entry_type = 'Run Sequence'

    def __init__(self, interval: timedelta, verbose: bool = False, **kwargs):
        self.interval = interval
        self.verbosity = ModelVerbosity.MAXIMUM if verbose else ModelVerbosity.MINIMUM

        self.__models = {}
        for key, value in kwargs.items():
            key = key.upper()
            if key in {entry.name for entry in ModelType} and \
                    isinstance(value, Model):
                self[ModelType[key]] = value
            elif key == 'EARTH' and isinstance(value, Earth):
                for model_type, model in value:
                    self[model_type] = model

        # set start and end processors
        for model_index, model in enumerate(self):
            next_model_index = model_index + 1
            if next_model_index < len(self):
                model.next = self.models[next_model_index]

        self.connections = []

    @property
    def models(self) -> [Model]:
        return [model for model_type, model in self.__models.items()
                if model_type in self]

    def connect(self, source: ModelType, destination: ModelType,
                method: RemapMethod = None):
        if method is None:
            method = RemapMethod.REDISTRIBUTE
        if source not in self.__models:
            raise ValueError(f'no {source.name} model in sequence')
        if destination not in self.__models:
            raise ValueError(f'no {destination.name} model in sequence')
        self.connections.append(Connection(source, destination, method))

    @property
    def earth(self) -> Earth:
        return Earth(self.verbosity, **{model.type.name: model
                                        for model in self.models})

    def append(self, model: Model):
        if model is not None:
            if len(self.models) > 0:
                self.models[-1].next = model
            self[model.type] = model

    def __getitem__(self, model_type: ModelType) -> Model:
        return self.__models[model_type]

    def __setitem__(self, model_type: ModelType, model: Model):
        assert model_type == model.type
        if model_type in self.__models:
            LOGGER.warning(f'overwriting existing "{model_type.name}" model')
        self.__models[model_type] = model

    def __contains__(self, model_type: ModelType):
        return model_type in self.__models

    def __iter__(self) -> Iterator[Model]:
        for model in self.models:
            yield model

    def __len__(self) -> int:
        return len(self.models)

    def __str__(self) -> str:
        block = '\n'.join(
            [str(connection) for connection in self.connections] + \
            [model_type.value for model_type in self.__models])
        block = '\n'.join([
            f'@{self.interval / timedelta(seconds=1):.0f}',
            indent(block, INDENTATION),
            '@'
        ])
        return '\n'.join([
            f'runSeq::',
            indent(block, INDENTATION),
            '::'
        ])

    def __repr__(self) -> str:
        models = [f'{model.type.name}={repr(model)}' for model in self.models]
        return f'{self.__class__.__name__}({repr(self.interval)}, {", ".join(models)})'


class Configuration:
    def __init__(self, model_sequence: ModelSequence):
        self.sequence = model_sequence

    @property
    def entries(self) -> [ConfigurationEntry]:
        return [self.sequence.earth, *self.sequence.models, self.sequence]

    def write(self, filename: PathLike, overwrite: bool = False):
        exists = os.path.exists(filename)
        if exists:
            LOGGER.warning(f'{"overwriting" if overwrite else "skipping"} '
                           f'existing file "{filename}"')
        if not exists or overwrite:
            with open(filename, 'w') as output_file:
                LOGGER.debug(f'writing NEMS configuration to "{filename}"')
                output_file.write(str(self))

    def __iter__(self) -> Iterator[ConfigurationEntry]:
        for entry in self.entries:
            yield entry

    def __getitem__(self, entry_type: type) -> [ConfigurationEntry]:
        return [entry for entry in self.entries
                if isinstance(entry, entry_type)]

    def __str__(self) -> str:
        return '#############################################\n' \
               '####  NEMS Run-Time Configuration File  #####\n' \
               '#############################################\n' \
               '\n' + \
               '\n'.join(f'# {entry.entry_type} #\n'
                         f'{entry}\n'
                         for entry in self.entries)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({repr(self.sequence)})'
