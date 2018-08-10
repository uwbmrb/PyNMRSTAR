import re

import pynmrstar
import loop
import saveframe
import entry


class Parser(object):
    """Parses an entry. You should not ever use this class directly."""

    reserved = ["stop_", "loop_", "save_", "data_", "global_"]

    def __init__(self, entry_to_parse_into=None):

        # Just make an entry to parse into if called with no entry passed
        if entry_to_parse_into is None:
            entry_to_parse_into = entry.Entry.from_scratch("")

        self.ent = entry_to_parse_into
        self.to_process = ""
        self.full_data = ""
        self.index = 0
        self.token = ""
        self.source = "unknown"
        self.delimiter = " "
        self.line_number = 0

    def get_line_number(self):
        """ Returns the current line number that is in the process of
        being parsed."""

        if pynmrstar.cnmrstar is not None:
            return self.line_number
        else:
            return self.full_data[0:self.index].count("\n") + 1

    def get_token(self):
        """ Returns the next token in the parsing process."""

        if pynmrstar.cnmrstar is not None:
            self.token, self.line_number, self.delimiter = pynmrstar.cnmrstar.get_token_full()
        else:
            self.real_get_token()
            self.line_number = 0

            if self.delimiter == ";":
                try:
                    # Unindent value which contain STAR multi-line values
                    # Only do this check if we are comma-delineated
                    if self.token.startswith("\n   "):
                        # Only remove the whitespaces if all lines have them
                        trim = True
                        for pos in range(1, len(self.token) - 4):
                            if self.token[pos] == "\n":
                                if self.token[pos + 1:pos + 4] != "   ":
                                    trim = False

                        if trim and "\n   ;" in self.token:
                            self.token = self.token[:-1].replace("\n   ", "\n")

                except AttributeError:
                    pass

        # This is just too VERBOSE
        if pynmrstar.VERBOSE == "very":
            if self.token:
                print("'%s': '%s'" % (self.delimiter, self.token))
            else:
                print("No more tokens.")

        # Return the token
        return self.token

    @staticmethod
    def index_handle(haystack, needle, start_pos=None):
        """ Finds the index while catching ValueError and returning
        None instead."""

        try:
            return haystack.index(needle, start_pos)
        except ValueError:
            return None

    @staticmethod
    def next_whitespace(data):
        """ Returns the position of the next whitespace character in the
        provided string. If no whitespace it returns the length of the
        string."""

        for pos, char in enumerate(data):
            if char in pynmrstar._WHITESPACE:
                return pos
        return len(data)

    def load_data(self, data):
        """ Loads data in preparation of parsing and cleans up newlines
        and massages the data to make parsing work properly when multiline
        values aren't as expected. Useful for manually getting tokens from
        the parser."""

        # Fix DOS line endings
        data = data.replace("\r\n", "\n").replace("\r", "\n")

        # Change '\n; data ' started multilines to '\n;\ndata'
        data = re.sub(r'\n;([^\n]+?)\n', r'\n;\n\1\n', data)

        if pynmrstar.cnmrstar is not None:
            pynmrstar.cnmrstar.load_string(data)
        else:
            self.full_data = data + "\n"

    def parse(self, data, source="unknown"):
        """ Parses the string provided as data as an NMR-STAR entry
        and returns the parsed entry. Raises ValueError on exceptions."""

        # Prepare the data for parsing
        self.load_data(data)

        # Create the NMRSTAR object
        curframe = None
        curloop = None
        curtag = None
        curdata = []

        # Get the first token
        self.get_token()

        # Make sure this is actually a STAR file
        if not self.token.startswith("data_"):
            raise ValueError("Invalid file. NMR-STAR files must start with"
                             " 'data_'. Did you accidentally select the wrong"
                             " file?", self.get_line_number())

        # Make sure there is a data name
        elif len(self.token) < 6:
            raise ValueError("'data_' must be followed by data name. Simply "
                             "'data_' is not allowed.", self.get_line_number())

        if self.delimiter != " ":
            raise ValueError("The data_ keyword may not be quoted or "
                             "semicolon-delineated.")

        # Set the entry_id
        self.ent.entry_id = self.token[5:]
        self.source = source

        # We are expecting to get saveframes
        while self.get_token() is not None:

            if not self.token.startswith("save_"):
                raise ValueError("Only 'save_NAME' is valid in the body of a "
                                 "NMR-STAR file. Found '" + self.token + "'.",
                                 self.get_line_number())

            if len(self.token) < 6:
                raise ValueError("'save_' must be followed by saveframe name. "
                                 "You have a 'save_' tag which is illegal "
                                 "without a specified saveframe name.",
                                 self.get_line_number())

            if self.delimiter != " ":
                raise ValueError("The save_ keyword may not be quoted or "
                                 "semicolon-delineated.",
                                 self.get_line_number())

            # Add the saveframe
            curframe = saveframe.Saveframe.from_scratch(self.token[5:], source=source)
            self.ent.add_saveframe(curframe)

            # We are in a saveframe
            while self.get_token() is not None:

                if self.token == "loop_":
                    if self.delimiter != " ":
                        raise ValueError("The loop_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())

                    curloop = loop.Loop.from_scratch(source=source)

                    # We are in a loop
                    seen_data = False
                    in_loop = True
                    while in_loop and self.get_token() is not None:

                        # Add a tag
                        if self.token.startswith("_"):
                            if self.delimiter != " ":
                                raise ValueError("Loop tags may not be quoted "
                                                 "or semicolon-delineated.",
                                                 self.get_line_number())
                            if seen_data:
                                raise ValueError("Cannot have more loop tags "
                                                 "after loop data.")
                            curloop.add_tag(self.token)

                        # On to data
                        else:

                            # Now that we have the tags we can add the loop
                            #  to the current saveframe
                            curframe.add_loop(curloop)

                            # We are in the data block of a loop
                            while self.token is not None:
                                if self.token == "stop_":
                                    if self.delimiter != " ":
                                        raise ValueError("The stop_ keyword may"
                                                         " not be quoted or "
                                                         "semicolon-delineated.",
                                                         self.get_line_number())
                                    if len(curloop.tags) == 0:
                                        if (pynmrstar.RAISE_PARSE_WARNINGS and
                                                "tag-only-loop" not in pynmrstar.WARNINGS_TO_IGNORE):
                                            raise ValueError("Loop with no "
                                                             "tags.", self.get_line_number())
                                        curloop = None
                                    if (not seen_data and
                                            pynmrstar.RAISE_PARSE_WARNINGS and
                                            "empty-loop" not in pynmrstar.WARNINGS_TO_IGNORE):
                                        raise ValueError("Loop with no data.",
                                                         self.get_line_number())
                                    else:
                                        if len(curdata) > 0:
                                            curloop.add_data(curdata,
                                                             rearrange=True)
                                        curloop = None
                                        curdata = []

                                    curloop = None
                                    in_loop = False
                                    break
                                else:
                                    if len(curloop.tags) == 0:
                                        raise ValueError("Data found in loop "
                                                         "before loop tags.",
                                                         self.get_line_number())

                                    if (self.token in self.reserved and
                                            self.delimiter == " "):
                                        raise ValueError("Cannot use keywords "
                                                         "as data values unless"
                                                         " quoted or semi-colon"
                                                         " delineated. Perhaps "
                                                         "this is a loop that "
                                                         "wasn't properly "
                                                         "terminated? Illegal "
                                                         "value: " + self.token,
                                                         self.get_line_number())
                                    curdata.append(self.token)
                                    seen_data = True

                                # Get the next token
                                self.get_token()

                    if self.token != "stop_":
                        raise ValueError("Loop improperly terminated at end of"
                                         " file.", self.get_line_number())

                # Close saveframe
                elif self.token == "save_":
                    if self.delimiter not in " ;":
                        raise ValueError("The save_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())
                    if not pynmrstar.ALLOW_V2_ENTRIES:
                        if curframe.tag_prefix is None:
                            raise ValueError("The tag prefix was never set! "
                                             "Either the saveframe had no tags,"
                                             " you tried to read a version 2.1 "
                                             "file without setting "
                                             "ALLOW_V2_ENTRIES to True, or "
                                             "there is something else wrong "
                                             "with your file. Saveframe error "
                                             "occured: '%s'" % curframe.name)
                    curframe = None
                    break

                # Invalid content in saveframe
                elif not self.token.startswith("_"):
                    raise ValueError("Invalid token found in saveframe '" +
                                     curframe.name + "': '" + self.token +
                                     "'", self.get_line_number())

                # Add a tag
                else:
                    if self.delimiter != " ":
                        raise ValueError("Saveframe tags may not be quoted or "
                                         "semicolon-delineated.",
                                         self.get_line_number())
                    curtag = self.token

                    # We are in a saveframe and waiting for the saveframe tag
                    self.get_token()
                    if self.delimiter == " ":
                        if self.token in self.reserved:
                            raise ValueError("Cannot use keywords as data values"
                                             " unless quoted or semi-colon "
                                             "delineated. Illegal value: " +
                                             self.token, self.get_line_number())
                        if self.token.startswith("_"):
                            raise ValueError("Cannot have a tag value start "
                                             "with an underscore unless the "
                                             "entire value is quoted. You may "
                                             "be missing a data value on the "
                                             "previous line. Illegal value: " +
                                             self.token, self.get_line_number())
                    curframe.add_tag(curtag, self.token, self.get_line_number())

            if self.token != "save_":
                raise ValueError("Saveframe improperly terminated at end of "
                                 "file.", self.get_line_number())

        # Free the memory of the original copy of the data we parsed
        self.full_data = None

        # Reset the parser
        if pynmrstar.cnmrstar is not None:
            pynmrstar.cnmrstar.reset()

        return self.ent

    def real_get_token(self):
        """ Actually processes the input data to find a token. get_token
        is just a wrapper around this with some exception handling."""

        # Reset the delimiter
        self.delimiter = " "

        # Nothing left
        if self.token is None:
            return

        # We're at the end if the index is the length
        if self.index == len(self.full_data):
            self.token = None
            return

        # Get just a single line of the file
        raw_tmp = ""
        tmp = ""
        while len(tmp) == 0:
            self.index += len(raw_tmp)

            try:
                newline_index = self.full_data.index("\n", self.index + 1)
                raw_tmp = self.full_data[self.index:newline_index]
            except ValueError:
                # End of file
                self.token = self.full_data[self.index:].lstrip(pynmrstar._WHITESPACE)
                if self.token == "":
                    self.token = None
                self.index = len(self.full_data)
                return

            newline_index = self.full_data.index("\n", self.index + 1)
            raw_tmp = self.full_data[self.index:newline_index + 1]
            tmp = raw_tmp.lstrip(pynmrstar._WHITESPACE)

        # If it is a multi-line comment, recalculate our viewing window
        if tmp[0:2] == ";\n":
            try:
                qstart = self.full_data.index(";\n", self.index)
                qend = self.full_data.index("\n;", qstart) + 3
            except ValueError:
                qstart = self.index
                qend = len(self.full_data)

            raw_tmp = self.full_data[self.index:qend]
            tmp = raw_tmp.lstrip()

        self.index += len(raw_tmp) - len(tmp)

        # Skip comments
        if tmp.startswith("#"):
            self.index += len(tmp)
            return self.get_token()

        # Handle multi-line values
        if tmp.startswith(";\n"):
            tmp = tmp[2:]

            # Search for end of multi-line value
            if "\n;" in tmp:
                until = tmp.index("\n;")
                valid = self.index_handle(tmp, "\n;\n")

                # The line is terminated properly
                if valid == until:
                    self.token = tmp[0:until + 1]
                    self.index += until + 4
                    self.delimiter = ";"
                    return

                # The line was terminated improperly
                else:
                    if self.next_whitespace(tmp[until + 2:]) == 0:
                        if (pynmrstar.RAISE_PARSE_WARNINGS and
                                "bad-multiline" not in pynmrstar.WARNINGS_TO_IGNORE):
                            raise ValueError("Warning: Technically invalid line"
                                             " found in file. Multiline values "
                                             "should terminate with \\n;\\n but"
                                             " in this file only \\n; with "
                                             "non-return whitespace following "
                                             "was found.",
                                             self.get_line_number())
                        self.token = tmp[0:until + 1]
                        self.index += until + 4
                        self.delimiter = ";"
                        return
                    else:
                        raise ValueError('Invalid file. A multi-line value '
                                         'ended with a "\\n;" and then a '
                                         'non-whitespace value. Multi-line '
                                         'values should end with "\\n;\\n".',
                                         self.get_line_number())
            else:
                raise ValueError("Invalid file. Multi-line comment never ends."
                                 " Multi-line comments must terminate with a "
                                 "line that consists ONLY of a ';' without "
                                 "characters before or after. (Other than the "
                                 "newline.)", self.get_line_number())

        # Handle values quoted with '
        if tmp.startswith("'"):
            until = self.index_handle(tmp, "'", 1)

            if until is None:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.get_line_number())

            # Make sure we don't stop for quotes that are not followed
            #  by whitespace
            try:
                while tmp[until + 1:until + 2] not in pynmrstar._WHITESPACE:
                    until = self.index_handle(tmp, "'", until + 1)
            except TypeError:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until + 1
            self.delimiter = "'"
            return

        # Handle values quoted with "
        if tmp.startswith('"'):
            until = self.index_handle(tmp, '"', 1)

            if until is None:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.get_line_number())

            # Make sure we don't stop for quotes that are not followed
            #  by whitespace
            try:
                while tmp[until + 1:until + 2] not in pynmrstar._WHITESPACE:
                    until = self.index_handle(tmp, '"', until + 1)
            except TypeError:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until + 1
            self.delimiter = '"'
            return

        # Figure out where this token ends
        white = self.next_whitespace(tmp)
        if white == len(tmp):
            self.token = tmp
            self.index += len(self.token) + 1
            if self.token[0] == "$" and len(self.token) > 1:
                self.delimiter = '$'
            return

        # The token isn't anything special, just return it
        self.index += white
        self.token = tmp[0:white]
        if self.token[0] == "$" and len(self.token) > 1:
            self.delimiter = '$'
        return
