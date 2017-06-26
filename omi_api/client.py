# Copyright 2017 ContextLabs B.V.

import time
import hashlib
import urllib
import requests
import sawtooth_signing as signing
from base64 import b64decode
from random import randint
from sawtooth_omi.protobuf.work_pb2 import Work
from sawtooth_omi.protobuf.recording_pb2 import Recording
from sawtooth_omi.protobuf.identity_pb2 import IndividualIdentity
from sawtooth_omi.protobuf.identity_pb2 import OrganizationalIdentity
from sawtooth_omi.protobuf.txn_payload_pb2 import OMITransactionPayload

from sawtooth_omi.handler import FAMILY_NAME, OMI_ADDRESS_PREFIX, make_omi_address, _get_address_infix
from sawtooth_omi.handler import WORK, RECORDING, INDIVIDUAL, ORGANIZATION

from sawtooth_sdk.protobuf.batch_pb2 import Batch
from sawtooth_sdk.protobuf.batch_pb2 import BatchHeader
from sawtooth_sdk.protobuf.batch_pb2 import BatchList
from sawtooth_sdk.protobuf.transaction_pb2 import Transaction
from sawtooth_sdk.protobuf.transaction_pb2 import TransactionHeader


TAG_MAP = {
    OrganizationalIdentity: ORGANIZATION,
    Recording: RECORDING,
    Work: WORK,
    IndividualIdentity: INDIVIDUAL,
}


def get_object_address(name, tag):
    return make_omi_address(name, tag)


def get_type_prefix(tag):
    return OMI_ADDRESS_PREFIX + _get_address_infix(tag)


class Cursor:
    def __init__(self, endpoint, message_type, count=100):
        self.endpoint = endpoint
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(endpoint).query)
        if 'count' not in qs:
            sep = '&' if qs else '?'
            self._next = "%s%scount=%d" % (self.endpoint, sep, count)
        else:
            self._next = self.endpoint
        self.message_type = message_type
        self.data = []

    def _get_page(self, url):
        r = requests.get(url)
        r.raise_for_status()
        result = r.json()
        paging = result['paging']
        if 'next' in paging:
            self._next = paging['next']
        else:
            self._next = None
        self.data.extend(result['data'])

    def _xform(self, item):
        # item['address']
        # item['data']
        return self.message_type.FromString(b64decode(item['data']))

    def __iter__(self):
        return self

    def __next__(self):
        if not self.data and self._next:
            self._get_page(self._next)
        if self.data:
            return self._xform(self.data.pop(0))
        raise StopIteration()


def submit_omi_transaction(base_url, private_key, action, message_type, natural_key_field, omi_obj, additional_inputs=None):
    obj = message_type(**omi_obj)

    if additional_inputs is None:
        additional_inputs = []

    public_key_hex = signing.generate_pubkey(private_key)

    address = get_object_address(omi_obj[natural_key_field], TAG_MAP[message_type])

    data = obj.SerializeToString()

    payload = OMITransactionPayload(
        action=action,
        data=data,
    )

    payload_bytes = payload.SerializeToString()
    payload_sha512 = hashlib.sha512(payload_bytes).hexdigest()

    txn_header = TransactionHeader(
        batcher_pubkey=public_key_hex,
        family_name=FAMILY_NAME,
        family_version='1.0',
        inputs=[address] + additional_inputs,
        outputs=[address],
        nonce=str(randint(0, 1000000000)),
        payload_encoding='application/protobuf',
        payload_sha512=payload_sha512,
        signer_pubkey=public_key_hex,
    )
    txn_header_bytes = txn_header.SerializeToString()

    key_handler = signing.secp256k1_signer._decode_privkey(private_key)

    # ecdsa_sign automatically generates a SHA-256 hash
    txn_signature = key_handler.ecdsa_sign(txn_header_bytes)
    txn_signature_bytes = key_handler.ecdsa_serialize_compact(txn_signature)
    txn_signature_hex = txn_signature_bytes.hex()

    # print([txn_signature_hex])

    txn = Transaction(
        header=txn_header_bytes,
        header_signature=txn_signature_hex,
        payload=payload_bytes,
    )

    batch_header = BatchHeader(
        signer_pubkey=public_key_hex,
        transaction_ids=[txn.header_signature],
    )

    batch_header_bytes = batch_header.SerializeToString()

    batch_signature = key_handler.ecdsa_sign(batch_header_bytes)
    batch_signature_bytes = key_handler.ecdsa_serialize_compact(batch_signature)
    batch_signature_hex = batch_signature_bytes.hex()

    batch = Batch(
        header=batch_header_bytes,
        header_signature=batch_signature_hex,
        transactions=[txn],
    )

    batch_list = BatchList(batches=[batch])
    batch_bytes = batch_list.SerializeToString()

    batch_id = batch_signature_hex

    url = "%s/batches" % base_url
    headers = {
        'Content-Type': 'application/octet-stream',
    }
    r = requests.post(url, data=batch_bytes, headers=headers)
    r.raise_for_status()
    link = r.json()['link']
    return BatchStatus(batch_id, link)


class BatchStatus:
    """
    Provides a function to query for the current status of a submitted transaction.
    That is, whether or not the transaction has been committed to the block chain.
    """

    def __init__(self, batch_id, status_url):
        self.batch_id = batch_id
        self.status_url = status_url

    def check(self, timeout=5):
        """
        Returns the batch status from a transaction submission. The status is one
        of ['PENDING', 'COMMITTED', 'INVALID', 'UNKNOWN'].
        """
        r = requests.get("%s&wait=%s" % (self.status_url, timeout))
        r.raise_for_status()
        return r.json()['data'][self.batch_id]

    def wait_for_committed(self, timeout=30, check_timeout=5):
        start_time = time.time()
        while True:
            current_time = time.time()
            status = self.check(timeout=check_timeout)
            if status == "PENDING":
                return status
            if start_time + timeout >= current_time:
                return status
        return status


class OMIClient:
    def __init__(self, sawtooth_rest_url, private_key, cursor_count=100):
        self.sawtooth_rest_url = sawtooth_rest_url
        self.private_key = private_key
        self.public_key = signing.generate_pubkey(private_key)
        self.cursor_count = cursor_count

    def _cursor(self, message_type):
        type_prefix = get_type_prefix(TAG_MAP[message_type])
        url = "%s/state?address=%s" % (self.sawtooth_rest_url, type_prefix)
        return Cursor(
            url,
            message_type,
            count=self.cursor_count
        )

    def _state_entry(self, message_type, name):
        address = get_object_address(name, TAG_MAP[message_type])
        url = "%s/state/%s" % (self.sawtooth_rest_url, address)
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()['data']
        return message_type.FromString(b64decode(data))

    def set_individual(self, individual):
        omi_obj = dict(individual)
        omi_obj['pubkey'] = self.public_key
        return submit_omi_transaction(
            base_url=self.sawtooth_rest_url,
            private_key=self.private_key,
            action='SetIndividualIdentity',
            message_type=IndividualIdentity,
            natural_key_field='name',
            omi_obj=omi_obj,
        )

    def get_individual(self, name):
        return self._state_entry(IndividualIdentity, name)

    def get_individuals(self):
        return self._cursor(IndividualIdentity)

    def set_organization(self, organization):
        omi_obj = dict(organization)
        omi_obj['pubkey'] = self.public_key
        return submit_omi_transaction(
            base_url=self.sawtooth_rest_url,
            private_key=self.private_key,
            action='SetOrganizationalIdentity',
            message_type=OrganizationalIdentity,
            natural_key_field='name',
            omi_obj=omi_obj,
        )

    def get_organization(self, name):
        return self._state_entry(OrganizationalIdentity, name)

    def get_organizations(self):
        return self._cursor(OrganizationalIdentity)

    def set_recording(self, recording):
        omi_obj = dict(recording)
        omi_obj['registering_pubkey'] = self.public_key
        label_name = omi_obj.get('label_name', None)
        contributor_splits = omi_obj.get('contributor_splits', [])
        derived_work_splits = omi_obj.get('derived_work_splits', [])
        derived_recording_splits = omi_obj.get('derived_recording_splits', [])
        references = []
        if label_name:
            references.append(get_object_address(label_name, ORGANIZATION))
        for split in contributor_splits:
            references.append(get_object_address(split['contributor_name'], INDIVIDUAL))
        for split in derived_work_splits:
            references.append(get_object_address(split['work_name'], WORK))
        for split in derived_recording_splits:
            references.append(get_object_address(split['recording_name'], RECORDING))

        return submit_omi_transaction(
            base_url=self.sawtooth_rest_url,
            private_key=self.private_key,
            action='SetRecording',
            message_type=Recording,
            natural_key_field='title',
            omi_obj=omi_obj,
            additional_inputs=references,
        )

    def get_recording(self, title):
        return self._state_entry(Recording, title)

    def get_recordings(self):
        return self._cursor(Recording)

    def set_work(self, work):
        omi_obj = dict(work)
        omi_obj['registering_pubkey'] = self.public_key
        songwriter_publisher_splits = omi_obj.get('songwriter_publisher_splits', [])
        references = []
        songwriter_publishers = [split['songwriter_publisher'] for split in songwriter_publisher_splits]
        for split in songwriter_publishers:
            references.append(get_object_address(split['songwriter_name'], INDIVIDUAL))
            references.append(get_object_address(split['publisher_name'], ORGANIZATION))

        return submit_omi_transaction(
            base_url=self.sawtooth_rest_url,
            private_key=self.private_key,
            action='SetWork',
            message_type=Work,
            natural_key_field='title',
            omi_obj=omi_obj,
            additional_inputs=references,
        )

    def get_work(self, title):
        return self._state_entry(Work, title)

    def get_works(self):
        return self._cursor(Work)
