import numpy as np


class Cable:
    # TODO:
    #   - use properties to compute r dynamically
    #   - track every use of the cable dict to make sure that... ?
    #   - check attributes values (with properties setter) for each attribute
    #   - add helpers strings

    # ensure that no attribues can de added without being declared here
    __slots__ = (
        "_length",
        "_area",
        "plugs_and_sockets",
        "_r",
        "phase",
        "nodes",
        "current",
        "vdrop_volts",
        "_coordinates",
        "_layer_name",
        "_id",
    )

    rho = 1 / 26  # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area

    def __init__(self, length: float, area: float, plugs_and_sockets: str):
        self.length = length
        self.area = area
        self.plugs_and_sockets = plugs_and_sockets
        self.nodes = []
        self.current = None

    @property
    def length(self):
        """This is the documentation for the length property.
        Note that length should be a float() and in meters.
        """
        return self._length

    @length.setter
    def length(self, value):
        assert isinstance(value, float), (
            f"cable length should be a float but is a {type(value)}"
        )
        assert value > 0, f"cable length is equal to 0m. This cable cannot be created."
        self._length = value

    @property
    def area(self):
        return self._area

    @area.setter
    def area(self, value):
        assert isinstance(value, float), (
            f"cable area should be a float but is {value} (which is a {type(value)})"
        )
        self._area = value

    @property
    def r(self):
        self._r = self.rho * self.length / self.area
        return self._r

    @property
    def coordinates(self):
        return self._coordinates

    @coordinates.setter
    def coordinates(self, value):
        self._coordinates = value


class Node:
    __slots__ = (
        "_name",
        "_parent",
        "_children",
        "_deepness",
        "_cable",
        "_cables",
        "_power",
        "_phase",
        "_date",
        "_cum_power",
        "_distro",
        "_coordinates",
        "_voltage",
        "_vdrop_percent",
    )

    def __init__(
        self,
        name: str,
    ):
        self.name = name
        self.parent = None
        self.children = None
        self.deepness = None
        self.cable = {}
        self.cables = []
        self.power = None
        self.phase = None
        self.date = None
        self.cum_power = np.array([0.0] * 3)
        self.distro = dict.fromkeys(["in", "out"])
        self.coordinates = None

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        assert isinstance(value, str), f"Node name must be a string, got {type(value)}"
        self._name = value

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, value):
        assert isinstance(value, str) or value is None, (
            "Parent must be a string or None"
        )
        self._parent = value

    @property
    def children(self):
        return self._children

    @children.setter
    def children(self, value):
        assert isinstance(value, dict) or value is None, (
            "Children must be a dict or None"
        )
        self._children = value

    @property
    def deepness(self):
        return self._deepness

    @deepness.setter
    def deepness(self, value):
        assert isinstance(value, int) or value is None, "Deepness must be int or None"
        self._deepness = value

    @property
    def cable(self):
        return self._cable

    @cable.setter
    def cable(self, value):
        assert isinstance(value, dict), "'cable' must be dict"
        self._cable = value

    @property
    def cables(self):
        return self._cables

    @cables.setter
    def cables(self, value):
        assert isinstance(value, list), "'cables' must be list"
        self._cables = value

    @property
    def power(self):
        return self._power

    @power.setter
    def power(self, value):
        self._power = value

    @property
    def phase(self):
        return self._phase

    @phase.setter
    def phase(self, value):
        self._phase = value

    @property
    def date(self):
        return self._date

    @date.setter
    def date(self, value):
        self._date = value

    @property
    def cum_power(self):
        return self._cum_power

    @cum_power.setter
    def cum_power(self, value):
        self._cum_power = value

    @property
    def distro(self):
        return self._distro

    @distro.setter
    def distro(self, value):
        assert isinstance(value, dict), "'distro' must be a dict"
        self._distro = value

    @property
    def coordinates(self):
        return self._coordinates

    @coordinates.setter
    def coordinates(self, value):
        self._coordinates = value

    @property
    def voltage(self):
        """voltage at the load, in Volts"""
        return self._voltage

    @voltage.setter
    def voltage(self, value):
        if isinstance(value, int):
            value = float(value)

        assert isinstance(value, float), (
            f"voltage should be a int or float, got {type(value)}"
        )
        self._voltage = value

    @property
    def vdrop_percent(self):
        """voltage drop at the load, in percents"""
        return self._vdrop_percent

    @vdrop_percent.setter
    def vdrop_percent(self, value):
        assert isinstance(value, float), (
            f"voltage drop should be float, got {type(value)}"
        )
        self._vdrop_percent = value
