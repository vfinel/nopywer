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
        """This is the documentation for the length property."""
        print("Note that length should be a float() and in meters.")
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
