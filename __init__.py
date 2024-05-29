import os.path
import time

from ovos_bus_client.message import Message
from ovos_config import Configuration
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler, adds_context, removes_context
from ovos_workshop.skills.auto_translatable import UniversalSkill


class DictationSkill(UniversalSkill):
    """
    - start dictation
      - enable continuous conversation mode
      - capture all utterances in converse method
    - converse
      - display dictation on screen live
    - stop dictation
      - restore listener mode
      - save dictation to file
      - display full dictation on screen
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the UniversalSkill with internal language set dynamically.
        """
        self.internal_language = "en-us"  # default to English
        super().__init__(internal_language=self.internal_language, autodetect=True, translate_tags=False, translate_keys=["utterance", "utterances"], *args, **kwargs)
        self.dictating = False
        self.awaiting_language = False

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(
            internet_before_load=False,
            network_before_load=False,
            gui_before_load=False,
            requires_internet=False,
            requires_network=False,
            requires_gui=False,
            no_internet_fallback=True,
            no_network_fallback=True,
            no_gui_fallback=True,
        )

    def initialize(self):
        self.dictating = False

    @property
    def default_listen_mode(self):
        listener_config = Configuration().get("listener", {})
        if listener_config.get("continuous_listen", False):
            return "continuous"
        elif listener_config.get("hybrid_listen", False):
            return "hybrid"
        else:
            return "wakeword"

    def ask_for_language(self):
        self.speak("In which language would you like me to translate? English, Dutch, Portuguese, or Polish?", expect_response=True)
        self.awaiting_language = True

    def set_language(self, language):
        language = language.lower()
        if language == "english":
            self.internal_language = "en-us"
        elif language == "dutch":
            self.internal_language = "nl-nl"
        elif language == "portuguese":
            self.internal_language = "pt-pt"
        elif language == "polish":
            self.internal_language = "pl-pl"
        else:
            self.speak("I did not understand the language. Please choose from English, Dutch, Portuguese, or Polish.")
            self.ask_for_language()
            return

        self.speak(f"Language set to {language.capitalize()}. Starting dictation.")
        self.awaiting_language = False
        self.start_dictation()

    @adds_context("DictationKeyword", "dictation")
    def start_dictation(self, message=None):
        message = message or Message("")
        self.dictation_stack = []
        self.dictating = True
        self.file_name = message.data.get("name", str(time.time()))
        self.bus.emit(message.forward("recognizer_loop:state.set",
                                      {"mode": "continuous"}))

    @removes_context("DictationKeyword")
    def stop_dictation(self, message=None):
        message = message or Message("")
        self.dictating = False
        self.bus.emit(message.forward("recognizer_loop:state.set",
                                      {"mode": self.default_listen_mode}))
        path = f"{os.path.expanduser('~')}/Documents/dictations"
        os.makedirs(path, exist_ok=True)
        name = self.file_name or str(time.time())
        with open(f"{path}/{name}.txt", "w") as f:
            f.write("\n".join(self.dictation_stack))
        self.gui.show_text(f"saved to {path}/{name}.txt")

    @intent_handler("start_dictation.intent")
    def handle_start_dictation_intent(self, message):
        if self.dictating:
            self.speak_dialog("already_dictating", wait=True)
        else:
            self.ask_for_language()

    @intent_handler("stop_dictation.intent")
    def handle_stop_dictation_intent(self, message):
        if self.dictating:
            self.speak_dialog("stop")
        else:
            self.speak_dialog("not_dictating")
        self.stop_dictation()

    def stop(self):
        if self.dictating:
            self.stop_dictation()
            return True

    def converse(self, message):
        utterance = message.data["utterances"][0]
        if self.awaiting_language:
            self.set_language(utterance)
            return True
        if self.dictating:
            if self.voc_match("StopKeyword", utterance):
                self.handle_stop_dictation_intent(message)
            else:
                self.gui.show_text(utterance)
                self.dictation_stack.append(utterance)
            return True
        return False
