# Copyright (c) 2019-2020 Manfred Moitzi
# License: MIT License
# Created 2019-03-09
from typing import TYPE_CHECKING, Iterable, List, cast
from ezdxf.lldxf import validator
from ezdxf.lldxf.attributes import (
    DXFAttr, DXFAttributes, DefSubclass, XType, RETURN_DEFAULT,
)
from ezdxf.lldxf.const import SUBCLASS_MARKER, DXF2000, DXF2010, DXFTypeError
from ezdxf.math import Vector
from .dxfentity import base_class, SubclassProcessor
from .dxfgfx import DXFGraphic, acdb_entity
from .dxfobj import DXFObject
from .factory import register_entity

if TYPE_CHECKING:
    from ezdxf.eztypes import (
        TagWriter, DXFNamespace, Drawing, Vertex, DXFTag, Matrix44,
    )

__all__ = ['Image', 'ImageDef', 'ImageDefReactor', 'RasterVariables', 'Wipeout']

acdb_image = DefSubclass('AcDbRasterImage', {
    'class_version': DXFAttr(90, dxfversion=DXF2000, default=0),
    'insert': DXFAttr(10, xtype=XType.point3d),

    # U-vector of a single pixel (points along the visual bottom of the image,
    # starting at the insertion point)
    'u_pixel': DXFAttr(11, xtype=XType.point3d),

    # V-vector of a single pixel (points along the visual left side of the
    # image, starting at the insertion point)
    'v_pixel': DXFAttr(12, xtype=XType.point3d),

    # Image size in pixels
    'image_size': DXFAttr(13, xtype=XType.point2d),

    # Hard reference to image def object
    'image_def_handle': DXFAttr(340),

    # Image display properties:
    # 1 = Show image
    # 2 = Show image when not aligned with screen
    # 4 = Use clipping boundary
    # 8 = Transparency is on
    'flags': DXFAttr(70, default=3),

    # Clipping state:
    # 0 = Off
    # 1 = On
    'clipping': DXFAttr(
        280, default=0,
        validator=validator.is_integer_bool,
        fixer=RETURN_DEFAULT,
    ),

    # Brightness value (0-100; default = 50)
    'brightness': DXFAttr(
        281, default=50,
        validator=validator.is_in_integer_range(0, 101),
        fixer=validator.fit_into_integer_range(0, 101),
    ),

    # Contrast value (0-100; default = 50)
    'contrast': DXFAttr(
        282, default=50,
        validator=validator.is_in_integer_range(0, 101),
        fixer=validator.fit_into_integer_range(0, 101),
    ),
    # Fade value (0-100; default = 0)
    'fade': DXFAttr(
        283, default=0,
        validator=validator.is_in_integer_range(0, 101),
        fixer=validator.fit_into_integer_range(0, 101),
    ),

    # Hard reference to image def reactor object, not required by AutoCAD
    'image_def_reactor_handle': DXFAttr(360),

    # Clipping boundary type:
    # 1 = Rectangular
    # 2 = Polygonal
    'clipping_boundary_type': DXFAttr(
        71, default=1,
        validator=validator.is_one_of({1, 2}),
        fixer=RETURN_DEFAULT
    ),

    # Number of clip boundary vertices that follow
    'count_boundary_points': DXFAttr(91),

    # Clip mode:
    # 0 = outside
    # 1 = inside mode
    'clip_mode': DXFAttr(
        290, dxfversion=DXF2010, default=0,
        validator=validator.is_integer_bool,
        fixer=RETURN_DEFAULT,
    ),
    # boundary path coordinates are pixel coordinates NOT drawing units
})


@register_entity
class Image(DXFGraphic):
    """ DXF IMAGE entity """
    DXFTYPE = 'IMAGE'
    DXFATTRIBS = DXFAttributes(base_class, acdb_entity, acdb_image)
    _CLS_ATTRIBS = acdb_image
    DEFAULT_ATTRIBS = {'layer': '0', 'flags': 3}
    MIN_DXF_VERSION_FOR_EXPORT = DXF2000

    SHOW_IMAGE = 1
    SHOW_IMAGE_WHEN_NOT_ALIGNED = 2
    USE_CLIPPING_BOUNDARY = 4
    USE_TRANSPARENCY = 8

    def __init__(self, doc: 'Drawing' = None):
        super().__init__(doc)
        self._boundary_path = []  # type: List[Vertex]

    def copy(self):
        raise DXFTypeError('Copying of IMAGE not supported.')

    def load_dxf_attribs(
            self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        dxf = super().load_dxf_attribs(processor)
        if processor:
            path_tags = processor.subclasses[2].pop_tags(codes=(14,))
            self.load_boundary_path(path_tags)
            tags = processor.load_dxfattribs_into_namespace(
                dxf, self._CLS_ATTRIBS)
            if len(tags):
                processor.log_unprocessed_tags(
                    tags, subclass=self._CLS_ATTRIBS.name)
            if len(self.boundary_path) < 2:  # something is wrong
                self.dxf = dxf
                self.reset_boundary_path()
        return dxf

    def load_boundary_path(self, tags: Iterable['DXFTag']):
        self._boundary_path = [value for code, value in tags if code == 14]

    @property
    def boundary_path(self):
        """ A list of vertices as pixel coordinates, Two vertices describe a
        rectangle, lower left corner is ``(-0.5, -0.5)`` and upper right corner
        is ``(ImageSizeX-0.5, ImageSizeY-0.5)``, more than two vertices is a
        polygon as clipping path. All vertices as pixel coordinates. (read/write)

        """
        return self._boundary_path

    @boundary_path.setter
    def boundary_path(self, vertices: Iterable['Vertex']) -> None:
        self.set_boundary_path(vertices)

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        """ Export entity specific data as DXF tags. """
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, self._CLS_ATTRIBS.name)
        self.dxf.count_boundary_points = len(self.boundary_path)
        self.dxf.export_dxf_attribs(tagwriter, [
            'class_version', 'insert', 'u_pixel', 'v_pixel', 'image_size',
            'image_def_handle', 'flags', 'clipping', 'brightness', 'contrast',
            'fade', 'image_def_reactor_handle', 'clipping_boundary_type',
            'count_boundary_points',
        ])
        self.export_boundary_path(tagwriter)
        if tagwriter.dxfversion >= DXF2010:
            self.dxf.export_dxf_attribs(tagwriter, 'clip_mode')

    def export_boundary_path(self, tagwriter: 'TagWriter'):
        for vertex in self.boundary_path:
            tagwriter.write_vertex(14, vertex[:2])

    def post_new_hook(self) -> None:
        self.reset_boundary_path()

    def set_boundary_path(self, vertices: Iterable['Vertex']) -> None:
        """ Set boundary path to `vertices`. Two vertices describe a rectangle
        (lower left and upper right corner), more than two vertices is a polygon
        as clipping path.

        """
        vertices = list(vertices)
        if len(vertices):
            if len(vertices) > 2 and vertices[-1] != vertices[0]:
                # Close path, otherwise AutoCAD crashes
                vertices.append(vertices[0])
            self._boundary_path = vertices
            self.set_flag_state(self.USE_CLIPPING_BOUNDARY, state=True)
            self.dxf.clipping = 1
            self.dxf.clipping_boundary_type = 1 if len(vertices) < 3 else 2
            self.dxf.count_boundary_points = len(self._boundary_path)
        else:
            self.reset_boundary_path()

    def reset_boundary_path(self) -> None:
        """ Reset boundary path to the default rectangle [(-0.5, -0.5),
        (ImageSizeX-0.5, ImageSizeY-0.5)].

        """
        lower_left_corner = (-.5, -.5)
        upper_right_corner = Vector(self.dxf.image_size) + lower_left_corner
        self._boundary_path = [lower_left_corner, upper_right_corner[:2]]
        self.set_flag_state(Image.USE_CLIPPING_BOUNDARY, state=False)
        self.dxf.clipping = 0
        self.dxf.clipping_boundary_type = 1
        self.dxf.count_boundary_points = 2

    def get_image_def(self) -> 'ImageDef':
        """ Returns the associated IMAGEDEF entity. see :class:`ImageDef`."""
        return cast('ImageDef', self.entitydb[self.dxf.image_def_handle])

    def destroy(self) -> None:
        image_def = self.get_image_def()
        reactor_handle = self.dxf.get('image_def_reactor_handle', None)
        if reactor_handle:
            # remove rectors
            image_def.discard_reactor_handle(reactor_handle)
            reactor = self.entitydb[reactor_handle]
            self.doc.objects.delete_entity(reactor)
        del self._boundary_path
        super().destroy()

    def transform(self, m: 'Matrix44') -> 'Image':
        """ Transform IMAGE entity by transformation matrix `m` inplace.

        .. versionadded:: 0.13

        """
        self.dxf.insert = m.transform(self.dxf.insert)
        self.dxf.u_pixel = m.transform_direction(self.dxf.u_pixel)
        self.dxf.v_pixel = m.transform_direction(self.dxf.v_pixel)
        return self


acdb_wipeout = DefSubclass('AcDbWipeout', dict(acdb_image.attribs))


@register_entity
class Wipeout(Image):
    """ DXF WIPEOUT entity """
    DXFTYPE = 'WIPEOUT'
    DXFATTRIBS = DXFAttributes(base_class, acdb_entity, acdb_wipeout)
    DEFAULT_ATTRIBS = {
        'layer': '0',
        'flags': 3,
        'image_size': (1, 1),
        'image_def_handle': '0',
        'image_def_reactor_handle': '0',
    }
    _CLS_ATTRIBS = acdb_wipeout


acdb_image_def = DefSubclass('AcDbRasterImageDef', {
    'class_version': DXFAttr(90, default=0),

    # File name of image:
    'filename': DXFAttr(1),

    # Image size in pixels:
    'image_size': DXFAttr(10, xtype=XType.point2d),

    # Default size of one pixel in AutoCAD units:
    'pixel_size': DXFAttr(11, xtype=XType.point2d, default=(.01, .01)),

    'loaded': DXFAttr(280, default=1),

    # Resolution units - this enums differ from the usual drawing units,
    # units.py, same as for RasterVariables.dxf.units, but only these 3 values
    # are valid - confirmed by ODA Specs 20.4.81 IMAGEDEF:
    # 0 = No units
    # 2 = Centimeters
    # 5 = Inch
    'resolution_units': DXFAttr(
        281, default=0,
        validator=validator.is_one_of({0, 2, 5}),
        fixer=RETURN_DEFAULT,
    ),

})


@register_entity
class ImageDef(DXFObject):
    """ DXF IMAGEDEF entity """
    DXFTYPE = 'IMAGEDEF'
    DXFATTRIBS = DXFAttributes(base_class, acdb_image_def)
    MIN_DXF_VERSION_FOR_EXPORT = DXF2000

    def load_dxf_attribs(
            self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.load_dxfattribs_into_namespace(dxf, acdb_image_def)
            if len(tags):
                processor.log_unprocessed_tags(
                    tags, subclass=acdb_image_def.name)
        return dxf

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        """ Export entity specific data as DXF tags. """
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_image_def.name)
        self.dxf.export_dxf_attribs(tagwriter, [
            'class_version', 'filename', 'image_size', 'pixel_size', 'loaded',
            'resolution_units',
        ])


acdb_image_def_reactor = DefSubclass('AcDbRasterImageDefReactor', {
    'class_version': DXFAttr(90, default=2),

    # Handle to image:
    'image_handle': DXFAttr(330),
})


@register_entity
class ImageDefReactor(DXFObject):
    """ DXF IMAGEDEF_REACTOR entity """
    DXFTYPE = 'IMAGEDEF_REACTOR'
    DXFATTRIBS = DXFAttributes(base_class, acdb_image_def_reactor)
    MIN_DXF_VERSION_FOR_EXPORT = DXF2000

    def load_dxf_attribs(
            self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.load_dxfattribs_into_namespace(
                dxf, acdb_image_def_reactor)
            if len(tags):
                processor.log_unprocessed_tags(
                    tags, subclass=acdb_image_def_reactor.name)
        return dxf

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        """ Export entity specific data as DXF tags. """
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_image_def_reactor.name)
        tagwriter.write_tag2(90, self.dxf.class_version)
        tagwriter.write_tag2(330, self.dxf.image_handle)


acdb_raster_variables = DefSubclass('AcDbRasterVariables', {
    'class_version': DXFAttr(90, default=0),

    # Frame:
    # 0 = no frame
    # 1 = show frame
    'frame': DXFAttr(
        70, default=0,
        validator=validator.is_integer_bool,
        fixer=RETURN_DEFAULT,
    ),
    # Quality:
    # 0 = draft
    # 1 = high
    'quality': DXFAttr(
        71, default=1,
        validator=validator.is_integer_bool,
        fixer=RETURN_DEFAULT,
    ),
    # Units:
    # 0 = None
    # 1 = mm
    # 2 = cm
    # 3 = m
    # 4 = km
    # 5 = in
    # 6 = ft
    # 7 = yd
    # 8 = mi
    'units': DXFAttr(
        72, default=3,
        validator=validator.is_in_integer_range(0, 9),
        fixer=RETURN_DEFAULT,
    ),

})


@register_entity
class RasterVariables(DXFObject):
    """ DXF RASTERVARIABLES entity """
    DXFTYPE = 'RASTERVARIABLES'
    DXFATTRIBS = DXFAttributes(base_class, acdb_raster_variables)
    MIN_DXF_VERSION_FOR_EXPORT = DXF2000

    def load_dxf_attribs(
            self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.load_dxfattribs_into_namespace(
                dxf, acdb_raster_variables)
            if len(tags):
                processor.log_unprocessed_tags(
                    tags, subclass=acdb_raster_variables.name)
        return dxf

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        """ Export entity specific data as DXF tags. """
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_raster_variables.name)
        self.dxf.export_dxf_attribs(tagwriter, [
            'class_version', 'frame', 'quality', 'units',
        ])


acdb_wipeout_variables = DefSubclass('AcDbWipeoutVariables', {
    # Display-image-frame flag:
    # 0 = No frame
    # 1 = Display frame
    'frame': DXFAttr(
        70, default=0,
        validator=validator.is_integer_bool,
        fixer=RETURN_DEFAULT,
    ),

})


@register_entity
class WipeoutVariables(DXFObject):
    """ DXF WIPEOUTVARIABLES entity """
    DXFTYPE = 'WIPEOUTVARIABLES'
    DXFATTRIBS = DXFAttributes(base_class, acdb_wipeout_variables)
    MIN_DXF_VERSION_FOR_EXPORT = DXF2000

    def load_dxf_attribs(
            self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.load_dxfattribs_into_namespace(
                dxf, acdb_wipeout_variables)
            if len(tags):
                processor.log_unprocessed_tags(
                    tags, subclass=acdb_wipeout_variables.name)
        return dxf

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        """ Export entity specific data as DXF tags. """
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_wipeout_variables.name)
        self.dxf.export_dxf_attribs(tagwriter, 'frame')
