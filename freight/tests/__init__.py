from datetime import datetime, timedelta
import logging
import random
import os
import string

from django.db.models import signals
from ..models import Pricing
from ..signals import pricing_save_handler


def dt_eveformat(dt: object) -> str:
    """converts a datetime to a string in eve format
    e.g. '2019-06-25T19:04:44'
    """
    from datetime import datetime

    dt2 = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return dt2.isoformat()


def set_logger(logger_name: str, name: str) -> object:
    """set logger for current test module
    
    Args:
    - logger: current logger object
    - name: name of current module, e.g. __file__
    
    Returns:
    - amended logger
    """

    # reconfigure logger so we get logging from tested module
    f_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s:%(funcName)s - %(message)s'
    )
    f_handler = logging.FileHandler(
        '{}.log'.format(os.path.splitext(name)[0]),
        'w+'
    )
    f_handler.setFormatter(f_format)
    logger = logging.getLogger(logger_name)
    logger.level = logging.DEBUG
    logger.addHandler(f_handler)
    logger.propagate = False
    return logger


class TempDisconnectSignal():
    """ Temporarily disconnect a model from a signal """
    def __init__(self, signal, receiver, sender, dispatch_uid=None):
        self.signal = signal
        self.receiver = receiver
        self.sender = sender
        self.dispatch_uid = dispatch_uid

    def __enter__(self):
        self.signal.disconnect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid
        )

    def __exit__(self, type, value, traceback):
        self.signal.connect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid
        )

class TempDisconnectPricingSaveHandler(TempDisconnectSignal):
    def __init__(self):
        super().__init__(
            signal=signals.post_save, 
            receiver=pricing_save_handler, 
            sender=Pricing, 
            dispatch_uid="id_update_contracts_pricing"
        )


def generate_token(
    character_id: int, 
    character_name: str,
    access_token: str = 'access_token',
    refresh_token: str = 'refresh_token',    
    scopes: list = None,
    timestamp_dt: object = None,
    expires_in: int  = 1200,
) -> dict:
    
    if timestamp_dt is None:
        timestamp_dt = datetime.utcnow()
    if scopes is None:
        scopes = [            
            'esi-mail.read_mail.v1',
            'esi-wallet.read_character_wallet.v1',
            'esi-universe.read_structures.v1'
        ]
    token = {
        'access_token': access_token,
        'token_type': 'Bearer',
        'expires_in': expires_in,
        'refresh_token': refresh_token,
        'timestamp': int(timestamp_dt.timestamp()),
        'CharacterID': character_id,
        'CharacterName': character_name,
        'ExpiresOn': dt_eveformat(timestamp_dt + timedelta(seconds=expires_in)),  
        'Scopes': ' '.join(list(scopes)),
        'TokenType': 'Character',
        'CharacterOwnerHash': get_random_string(28),
        'IntellectualProperty': 'EVE'
    }
    return token


def store_as_Token(token: dict, user: object) -> object:
    """Stores a generated token dict as Token object for given user
    
    returns Token object
    """    
    from esi.models import Scope, Token
    
    obj = Token.objects.create(
        access_token=token['access_token'],
        refresh_token=token['refresh_token'],
        user=user,
        character_id=token['CharacterID'],
        character_name=token['CharacterName'],
        token_type=token['TokenType'],
        character_owner_hash=token['CharacterOwnerHash'],        
    )    
    for scope_name in token['Scopes'].split(' '):
        scope, _ = Scope.objects.get_or_create(
            name=scope_name
        )
        obj.scopes.add(scope)

    return obj


def get_random_string(char_count):    
    return ''.join(
        random.choice(string.ascii_uppercase + string.digits) 
        for _ in range(char_count)
    )

