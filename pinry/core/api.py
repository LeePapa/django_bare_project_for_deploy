from django.core.exceptions import ObjectDoesNotExist
from tastypie import fields
from tastypie.authorization import DjangoAuthorization
from tastypie.constants import ALL, ALL_WITH_RELATIONS
from tastypie.exceptions import Unauthorized
from tastypie.resources import ModelResource
from django_images.models import Thumbnail

from .models import Pin, Image
from vote.models import Vote
from ..users.models import User


class PinryAuthorization(DjangoAuthorization):
    """
    Pinry-specific Authorization backend with object-level permission checking.
    """

    def create_detail(self, object_list, bundle):
        klass = self.base_checks(bundle.request, bundle.obj.__class__)

        if klass is False:
            raise Unauthorized("You are not allowed to access that resource.")

        permission = '%s.add_%s' % (klass._meta.app_label, klass._meta.model_name)
        print bundle.request.user.has_perm(permission)
        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("You are not allowed to access that resource.")

        return True

    def update_detail(self, object_list, bundle):
        klass = self.base_checks(bundle.request, bundle.obj.__class__)

        if klass is False:
            raise Unauthorized("You are not allowed to access that resource.")

        permission = '%s.change_%s' % (klass._meta.app_label, klass._meta.model_name)

        if not bundle.request.user.has_perm(permission, bundle.obj):
            raise Unauthorized("You are not allowed to access that resource.")

        return True

    def delete_detail(self, object_list, bundle):
        klass = self.base_checks(bundle.request, bundle.obj.__class__)
        print bundle.obj.__class__
        if klass is False:
            raise Unauthorized("You are not allowed to access that resource.")

        print dir(klass._meta)
        permission = '%s.delete_%s' % (klass._meta.app_label, klass._meta.model_name)

        if not bundle.request.user.has_perm(permission, bundle.obj):
            raise Unauthorized("You are not allowed to access that resource.")

        return True


class UserResource(ModelResource):
    gravatar = fields.CharField(readonly=True)

    def dehydrate_gravatar(self, bundle):
        return bundle.obj.gravatar

    class Meta:
        list_allowed_methods = ['get']
        filtering = {
            'username': ALL
        }
        queryset = User.objects.all()
        resource_name = 'user'
        fields = ['username']
        include_resource_uri = False




def filter_generator_for(size):
    def wrapped_func(bundle, **kwargs):
        if hasattr(bundle.obj, '_prefetched_objects_cache') and 'thumbnail' in bundle.obj._prefetched_objects_cache:
            for thumbnail in bundle.obj._prefetched_objects_cache['thumbnail']:
                if thumbnail.size == size:
                    return thumbnail
            raise ObjectDoesNotExist()
        else:
            return bundle.obj.get_by_size(size)
    return wrapped_func


class ThumbnailResource(ModelResource):
    class Meta:
        list_allowed_methods = ['get']
        fields = ['image', 'width', 'height']
        queryset = Thumbnail.objects.all()
        resource_name = 'thumbnail'
        include_resource_uri = False


class ImageResource(ModelResource):
    standard = fields.ToOneField(ThumbnailResource, full=True,
                                 attribute=lambda bundle: filter_generator_for('standard')(bundle))
    thumbnail = fields.ToOneField(ThumbnailResource, full=True,
                                  attribute=lambda bundle: filter_generator_for('thumbnail')(bundle))
    square = fields.ToOneField(ThumbnailResource, full=True,
                               attribute=lambda bundle: filter_generator_for('square')(bundle))

    class Meta:
        fields = ['image', 'width', 'height']
        include_resource_uri = False
        resource_name = 'image'
        queryset = Image.objects.all()
        authorization = DjangoAuthorization()


class PinResource(ModelResource):
    submitter = fields.ToOneField(UserResource, 'submitter', full=True)
    image = fields.ToOneField(ImageResource, 'image', full=True)
    tags = fields.ListField()
    # num_iid = fields.IntegerField(unique=True)

    def hydrate_image(self, bundle):
        url = bundle.data.get('url', None)
        if url:
            image = Image.objects.create_for_url(url)
            bundle.data['image'] = '/api/v1/image/{}/'.format(image.pk)
        return bundle

    def hydrate(self, bundle):
        """Run some early/generic processing

        Make sure that user is authorized to create Pins first, before
        we hydrate the Image resource, creating the Image object in process
        """
        submitter = bundle.data.get('submitter', None)
        if not submitter:
            bundle.data['submitter'] = '/api/v1/user/{}/'.format(bundle.request.user.pk)
        else:
            if not '/api/v1/user/{}/'.format(bundle.request.user.pk) == submitter:
                raise Unauthorized("You are not authorized to create Pins for other users")
        return bundle

    def dehydrate_tags(self, bundle):
        return map(str, bundle.obj.tags.all())

    def build_filters(self, filters=None):
        orm_filters = super(PinResource, self).build_filters(filters)
        if filters and 'tag' in filters:
            orm_filters['tags__name__in'] = filters['tag'].split(',')
        return orm_filters

    def save_m2m(self, bundle):
        tags = bundle.data.get('tags', None)
        if tags:
            bundle.obj.tags.set(*tags)
        return super(PinResource, self).save_m2m(bundle)

    class Meta:
        fields = ['id', 'url', 'origin', 'description','price','tao_kouling','num_iid']
        ordering = ['id']
        filtering = {
            'submitter': ALL_WITH_RELATIONS
        }
        queryset = Pin.objects.all().select_related('submitter', 'image'). \
            prefetch_related('image__thumbnail_set', 'tags')
        resource_name = 'pin'
        include_resource_uri = False
        always_return_data = True
        authorization = PinryAuthorization()

# this api returns pins which are voted by the current requesting user.
# class LikeResource(ModelResource):
#     class Meta:
#         queryset = Pin.objects.all()
#         resource_name = 'like'
#         filtering = {
#             'user': ALL_WITH_RELATIONS,
#             'user_id': ALL_WITH_RELATIONS,
#         }
#     def get_object_list(self, request):
#         return super(LikeResource, self).get_object_list(request).filter(votes__user_id=request.user.id)

class LikeResource(PinResource):
    submitter = fields.ToOneField(UserResource, 'submitter', full=True)


    image = fields.ToOneField(ImageResource, 'image', full=True)
    tags = fields.ListField()
    class Meta:
        fields = ['id', 'url', 'origin', 'description', 'price']
        ordering = ['id']
        filtering = {
            'submitter': ALL_WITH_RELATIONS
        }
        queryset = Pin.objects.all().select_related('submitter', 'image'). \
            prefetch_related('image__thumbnail_set', 'tags')
        resource_name = 'like'
        include_resource_uri = False
        always_return_data = True
        authorization = PinryAuthorization()
    def get_object_list(self, request):
        return super(LikeResource, self).get_object_list(request).filter(votes__user_id=request.user.id)

# def like_api(request):
#     liked_pins = Pin.objects.all(user_id=request.user.id)
#     from django.utils import simplejson
#
#     some_data_to_dump = {
#        'some_var_1': 'foo',
#        'some_var_2': 'bar',
#     }
#
#     data = simplejson.dumps(some_data_to_dump)
#     return
