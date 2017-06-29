from rest_framework.routers import DefaultRouter, Route, DynamicListRoute, DynamicDetailRoute
from .views import OrganizationsViewSet, WorksViewSet, IndividualsViewSet, RecordingsViewSet


class OMIRouter(DefaultRouter):
    routes = [
        # List route.
        Route(
            url=r'^{prefix}{trailing_slash}(;.+)?$',
            mapping={
                'get': 'list',
                'post': 'create'
            },
            name='{basename}-list',
            initkwargs={'suffix': 'List'}
        ),
        # Dynamically generated list routes.
        # Generated using @list_route decorator
        # on methods of the viewset.
        DynamicListRoute(
            url=r'^{prefix}/{methodname}{trailing_slash}$',
            name='{basename}-{methodnamehyphen}',
            initkwargs={}
        ),
        # Detail route.
        Route(
            url=r'^{prefix}/{lookup}{trailing_slash}$',
            mapping={
                'get': 'retrieve',
                'put': 'update',
                'patch': 'partial_update',
                'delete': 'destroy'
            },
            name='{basename}-detail',
            initkwargs={'suffix': 'Instance'}
        ),
        # Dynamically generated detail routes.
        # Generated using @detail_route decorator on methods of the viewset.
        DynamicDetailRoute(
            url=r'^{prefix}/{lookup}/{methodname}{trailing_slash}$',
            name='{basename}-{methodnamehyphen}',
            initkwargs={}
        ),
    ]


router = OMIRouter()
router.register(r'works', WorksViewSet, base_name="works")
router.register(r'recordings', RecordingsViewSet, base_name="recordings")
router.register(r'organizations', OrganizationsViewSet, base_name="organizations")
router.register(r'individuals', IndividualsViewSet, base_name="individuals")
api_urlpatterns = router.urls
