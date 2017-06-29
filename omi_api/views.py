import re
import urllib

from django.conf import settings
from rest_framework import viewsets
from rest_framework.response import Response
from requests.exceptions import HTTPError
from protobuf_to_dict import protobuf_to_dict

from omi_api.client import OMIClient


class OMISTLViewSet(viewsets.ViewSet):
    headers = {
        'X-OMI-Version': '1.0',
    }

    def _to_json(self, item):
        return self.transform(protobuf_to_dict(item))

    def transform(self, item):
        return item

    def _parse_limit_offset(self, request):
        limit = 10
        offset = 0
        full_path = urllib.parse.unquote(request.get_full_path())
        if ';limit=' in full_path:
            limit = int(re.match(".*;limit=(\d+)", full_path).groups()[0])
        if ';offset=' in full_path:
            offset = int(re.match(".*;offset=(\d+)", full_path).groups()[0])
        if limit < 1 or limit > 1000:
            limit = 10
        if offset < 1:
            offset = 0
        return limit, offset

    def _parse_query(self, request):
        query = urllib.parse.urlparse(request.get_full_path()).query
        if query:
            return urllib.parse.parse_qs(query)
        return {}

    def _filter_item(self, item, query):
        """ Returns true if the item is included in the query """
        if not query:
            return True

        for k, query_values in query.items():
            _not = k.endswith("!")
            if _not:
                k = k[:-1]
            if k in item:
                item_value = item[k]
                for value in query_values:
                    if value == "*":
                        if _not:
                            return False
                    elif value.startswith("*") and value.endswith("*"):
                        value = value.strip("*")
                        if value in item_value:
                            if _not:
                                return False
                        else:
                            return False
                    elif value.startswith("*"):
                        value = value.strip("*")
                        if item_value.endswith(value):
                            if _not:
                                return False
                        else:
                            return False
                    elif value.endswith("*"):
                        value = value.strip("*")
                        if item_value.startswith(value):
                            if _not:
                                return False
                        else:
                            return False
                    else:
                        if value == item_value:
                            if _not:
                                return False
                        else:
                            return False
        return True

    def _filter_and_paginate(self, request, collection):
        limit, offset = self._parse_limit_offset(request)
        query = self._parse_query(request)
        total = 0
        results = []
        for item in collection:
            item = self._to_json(item)
            if self._filter_item(item, query):
                if total >= offset and not len(results) >= limit:
                    results.append(item)
                total += 1
        return {
            'count': len(results),
            'total': total,
            'offset': offset,
            'results': results,
        }


class IndividualsViewSet(OMISTLViewSet):
    """
    Viewset to list all or retreive a single individual in the system.
    """

    def transform(self, item):
        return {
            'ext': item,
        }

    def list(self, request, *args, **kwargs):
        """
        Return a list of all individuals.
        """

        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        return Response(self._filter_and_paginate(request, client.get_individuals()))

    def retrieve(self, request, pk=None):
        """
        Return an individual.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        try:
            return Response(self._to_json(client.get_individual(pk)))
        except HTTPError as exc:
            if exc.response.status_code == 404:
                return Response(status=404, headers=self.headers)
            raise

    def create(self, request, *args, **kwargs):
        """
        Register an individual.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        status = client.set_individual(request.data)
        if status.wait_for_committed() == "COMMITTED":
            return Response(status=201, headers=self.headers)
        else:
            return Response({'sawtooth_batch_status': status}, status=500, headers=self.headers)


class OrganizationsViewSet(OMISTLViewSet):
    """
    Viewset to list all or retreive a single organization in the system.
    """

    def transform(self, item):
        return {
            'ext': item,
        }

    def list(self, request, *args, **kwargs):
        """
        Return a list of all organisations.
        """

        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        return Response(self._filter_and_paginate(request, client.get_organizations()), headers=self.headers)

    def retrieve(self, request, pk=None):
        """
        Return an organisations.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        try:
            return Response(self._to_json(client.get_organization(pk)), headers=self.headers)
        except HTTPError as exc:
            if exc.response.status_code == 404:
                return Response(status=404, headers=self.headers)
            raise

    def create(self, request, *args, **kwargs):
        """
        Register an organisation.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        status = client.set_organization(request.data)
        if status.wait_for_committed() == "COMMITTED":
            return Response(status=201, headers=self.headers)
        else:
            return Response({'sawtooth_batch_status': status}, status=500, headers=self.headers)


class WorksViewSet(OMISTLViewSet):
    """
    Viewset to list all or retreive a single work in the system.
    """

    def transform(self, item):
        ext = {}
        for k in ("registering_pubkey", "songwriter_publisher_splits"):
            value = item.pop(k)
            if value:
                ext[k] = value
        if ext:
            item['ext'] = ext
        return item

    def list(self, request, *args, **kwargs):
        """
        Return a list of all works.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        return Response(self._filter_and_paginate(request, client.get_works()), headers=self.headers)

    def retrieve(self, request, pk=None):
        """
        Return a work.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        try:
            return Response(self._to_json(client.get_work(pk)), headers=self.headers)
        except HTTPError as exc:
            if exc.response.status_code == 404:
                return Response(status=404, headers=self.headers)
            raise

    def create(self, request, *args, **kwargs):
        """
        Register a work.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        status = client.set_work(request.data)
        if status.wait_for_committed() == "COMMITTED":
            return Response(status=201, headers=self.headers)
        else:
            return Response({'sawtooth_batch_status': status}, status=500, headers=self.headers)


class RecordingsViewSet(OMISTLViewSet):
    """
    Viewset to list all or retreive a single recording in the system.
    """

    def transform(self, item):
        ext = {}
        for k in ("registering_pubkey", "contributor_splits", "derived_work_splits", "overall_split"):
            value = item.pop(k)
            if value:
                ext[k] = value
        if ext:
            item['ext'] = ext
        return item

    def list(self, request, *args, **kwargs):
        """
        Return a list of all recording.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        return Response(self._filter_and_paginate(request, client.get_recordings()), headers=self.headers)

    def retrieve(self, request, pk=None):
        """
        Return a recording.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        try:
            return Response(self._to_json(client.get_recording(pk)), headers=self.headers)
        except HTTPError as exc:
            if exc.response.status_code == 404:
                return Response(status=404, headers=self.headers)
            raise

    def create(self, request, *args, **kwargs):
        """
        Register a recording.
        """
        client = OMIClient(settings.STL_REST_URL, settings.STL_PRIVKEY)
        data = dict(request.data)
        omi_stl_map = {
            'title': 'title',
            'isrc': 'ISRC',
        }
        for kr, kd in omi_stl_map.items():
            if kr in data:
                data[kd] = data.pop(kr)

        labels = data.pop('labels')
        if labels:
            if len(labels) > 1:
                return Response({'error': "Sawtooth only supports one label"}, status=400, headers=self.headers)
            try:
                data['label_name'] = labels[0]['name']
            except KeyError:
                return Response({'error': "Missing 'name' for label"}, status=400, headers=self.headers)

        status = client.set_recording(data)
        result = status.wait_for_committed()
        if result == "COMMITTED":
            return Response(status=201, headers=self.headers)
        else:
            return Response({'sawtooth_batch_status': result}, status=500, headers=self.headers)
