import ctypes
from ctypes import wintypes
import sys


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
_ADVAPI32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True) if sys.platform == "win32" else None


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def gift_card_credential_target(card_id: int) -> str:
    return f"AutoZS/HomeDepot/GiftCard/{int(card_id)}"


def store_generic_credential(target: str, username: str, secret: str) -> None:
    _require_windows()
    target = str(target or "").strip()
    username = str(username or "").strip()
    secret = str(secret or "").strip()
    if not target or not username or not secret:
        raise ValueError("Credential target, card number, and PIN are required.")

    blob_bytes = secret.encode("utf-16-le")
    blob = ctypes.create_string_buffer(blob_bytes)
    credential = _Credential()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(blob_bytes)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = username

    cred_write = _ADVAPI32.CredWriteW
    cred_write.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    cred_write.restype = wintypes.BOOL
    if not cred_write(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def read_generic_credential(target: str) -> tuple[str, str]:
    _require_windows()
    credential_pointer = ctypes.POINTER(_Credential)()
    cred_read = _ADVAPI32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    cred_read.restype = wintypes.BOOL
    if not cred_read(str(target or "").strip(), CRED_TYPE_GENERIC, 0, ctypes.byref(credential_pointer)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        credential = credential_pointer.contents
        blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return str(credential.UserName or ""), blob.decode("utf-16-le")
    finally:
        _ADVAPI32.CredFree(credential_pointer)


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows Credential Manager is only available on the Windows AutoZS worker.")
