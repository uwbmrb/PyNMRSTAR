class ParsingError(Exception):
    """ Something is wrong with the server. """

    def __init__(self, message, line_number: int = None):
        Exception.__init__(self)
        self.message = message
        self.line_number = line_number

    def __repr__(self) -> str:
        if self.line_number is not None:
            return 'ParsingError("%s") on line %d' % (self.message, self.line_number)
        else:
            return 'ParsingError("%s")' % self.message

    def __str__(self) -> str:
        if self.line_number is not None:
            return "%s on line %d" % (self.message, self.line_number)
        else:
            return self.message
