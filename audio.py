import ctypes
import pythoncom
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL

class AudioController:
    def __init__(self):
        pass

    def _get_speakers_volume(self):
        """Get the speaker endpoint volume interface with COM initialized."""
        pythoncom.CoInitialize()
        try:
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                return speakers.EndpointVolume
        except Exception as e:
            print(f"Error activating speakers volume: {e}")
        return None

    def _get_microphone_volume(self):
        """Get the microphone endpoint volume interface with COM initialized."""
        pythoncom.CoInitialize()
        try:
            mic = AudioUtilities.GetMicrophone()
            if mic:
                mic_interface = mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                return ctypes.cast(mic_interface, ctypes.POINTER(IAudioEndpointVolume))
        except Exception as e:
            print(f"Error activating microphone volume: {e}")
        return None



    # --- Speaker Volume Controls ---
    
    def get_speaker_state(self):
        """Return (volume_scalar, is_muted)."""
        vol_interface = self._get_speakers_volume()
        if not vol_interface:
            return 0.0, False
        try:
            vol = vol_interface.GetMasterVolumeLevelScalar()
            muted = vol_interface.GetMute()
            return vol, bool(muted)
        except Exception as e:
            print(f"Error getting speaker state: {e}")
            return 0.0, False

    def toggle_speaker_mute(self):
        """Toggle system speaker mute and returns (new_mute_state, status_str)."""
        vol_interface = self._get_speakers_volume()
        if not vol_interface:
            return None, "No Playback Device Found"
        try:
            current_mute = vol_interface.GetMute()
            new_mute = not current_mute
            vol_interface.SetMute(new_mute, None)
            status = "MUTED" if new_mute else "UNMUTED"
            return new_mute, f"Speakers: {status}"
        except Exception as e:
            print(f"Error toggling speaker mute: {e}")
            return None, f"Speaker Error: {e}"

    def adjust_speaker_volume(self, step):
        """Increase or decrease volume by the step float (e.g. 0.05 or -0.05)."""
        vol_interface = self._get_speakers_volume()
        if not vol_interface:
            return None, "No Playback Device Found"
        try:
            # If muted, unmute first
            if vol_interface.GetMute():
                vol_interface.SetMute(False, None)
                
            current_vol = vol_interface.GetMasterVolumeLevelScalar()
            new_vol = max(0.0, min(1.0, current_vol + step))
            vol_interface.SetMasterVolumeLevelScalar(new_vol, None)
            pct = int(round(new_vol * 100))
            return pct, f"Volume: {pct}%"
        except Exception as e:
            print(f"Error adjusting speaker volume: {e}")
            return None, f"Volume Error: {e}"

    # --- Microphone Controls ---

    def get_mic_state(self):
        """Return (volume_scalar, is_muted)."""
        vol_interface = self._get_microphone_volume()
        if not vol_interface:
            return 0.0, False
        try:
            vol = vol_interface.GetMasterVolumeLevelScalar()
            muted = vol_interface.GetMute()
            return vol, bool(muted)
        except Exception as e:
            print(f"Error getting mic state: {e}")
            return 0.0, False

    def toggle_mic_mute(self):
        """Toggle system microphone mute and returns (new_mute_state, status_str)."""
        vol_interface = self._get_microphone_volume()
        if not vol_interface:
            return None, "No Capture Device Found"
        try:
            current_mute = vol_interface.GetMute()
            new_mute = not current_mute
            vol_interface.SetMute(new_mute, None)
            status = "MUTED" if new_mute else "UNMUTED"
            return new_mute, f"Microphone: {status}"
        except Exception as e:
            print(f"Error toggling mic mute: {e}")
            return None, f"Mic Error: {e}"

    def set_mic_volume(self, level_scalar):
        """Directly set microphone volume scalar (0.0 to 1.0)."""
        vol_interface = self._get_microphone_volume()
        if not vol_interface:
            return None, "No Capture Device Found"
        try:
            vol_interface.SetMasterVolumeLevelScalar(level_scalar, None)
            pct = int(round(level_scalar * 100))
            return pct, f"Mic Volume: {pct}%"
        except Exception as e:
            print(f"Error setting mic volume: {e}")
            return None, f"Mic Volume Error: {e}"
