#!/usr/bin python3
""" Utilities available across all scripts """

import logging
import os
import warnings

from hashlib import sha1
from pathlib import Path
from re import finditer

import cv2
import numpy as np

import dlib

from lib.faces_detect import DetectedFace


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

# Global variables
_image_extensions = [  # pylint: disable=invalid-name
    ".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff"]
_video_extensions = [  # pylint: disable=invalid-name
    ".avi", ".flv", ".mkv", ".mov", ".mp4", ".mpeg", ".webm"]


def get_folder(path):
    """ Return a path to a folder, creating it if it doesn't exist """
    logger.debug("Requested path: '%s'", path)
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Returning: '%s'", output_dir)
    return output_dir


def get_image_paths(directory):
    """ Return a list of images that reside in a folder """
    image_extensions = _image_extensions
    dir_contents = list()

    if not os.path.exists(directory):
        logger.debug("Creating folder: '%s'", directory)
        directory = get_folder(directory)

    dir_scanned = sorted(os.scandir(directory), key=lambda x: x.name)
    logger.debug("Scanned Folder contains %s files", len(dir_scanned))
    logger.trace("Scanned Folder Contents: %s", dir_scanned)

    for chkfile in dir_scanned:
        if any([chkfile.name.lower().endswith(ext)
                for ext in image_extensions]):
            logger.trace("Adding '%s' to image list", chkfile.path)
            dir_contents.append(chkfile.path)

    logger.debug("Returning %s images", len(dir_contents))
    return dir_contents


def hash_image_file(filename):
    """ Return an image file's sha1 hash """
    img = cv2.imread(filename)  # pylint: disable=no-member
    img_hash = sha1(img).hexdigest()
    logger.trace("filename: '%s', hash: %s", filename, img_hash)
    return img_hash


def hash_encode_image(image, extension):
    """ Encode the image, get the hash and return the hash with
        encoded image """
    img = cv2.imencode(extension, image)[1]  # pylint: disable=no-member
    f_hash = sha1(
        cv2.imdecode(img, cv2.IMREAD_UNCHANGED)).hexdigest()  # pylint: disable=no-member
    return f_hash, img


def set_system_verbosity():
    """ Set the verbosity level of tensorflow and suppresses
        future and deprecation warnings from any modules
        From:
        https://stackoverflow.com/questions/35911252/disable-tensorflow-debugging-information
        Can be set to:
        0 - all logs shown
        1 - filter out INFO logs
        2 - filter out WARNING logs
        3 - filter out ERROR logs  """

    loglevel = "2" if logger.getEffectiveLevel() > 15 else "0"
    logger.debug("System Verbosity level: %s", loglevel)
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = loglevel
    if loglevel != '0':
        for warncat in (FutureWarning, DeprecationWarning):
            warnings.simplefilter(action='ignore', category=warncat)


def add_alpha_channel(image, intensity=100):
    """ Add an alpha channel to an image

        intensity: The opacity of the alpha channel between 0 and 100
                   100 = transparent,
                   0 = solid  """
    logger.trace("Adding alpha channel: intensity: %s", intensity)
    assert 0 <= intensity <= 100, "Invalid intensity supplied"
    intensity = (255.0 / 100.0) * intensity

    d_type = image.dtype
    image = image.astype("float32")

    ch_b, ch_g, ch_r = cv2.split(image)  # pylint: disable=no-member
    ch_a = np.ones(ch_b.shape, dtype="float32") * intensity

    image_bgra = cv2.merge(  # pylint: disable=no-member
        (ch_b, ch_g, ch_r, ch_a))
    logger.trace("Added alpha channel", intensity)
    return image_bgra.astype(d_type)


def rotate_landmarks(face, rotation_matrix):
    # pylint: disable=c-extension-no-member
    """ Rotate the landmarks and bounding box for faces
        found in rotated images.
        Pass in a DetectedFace object, Alignments dict or DLib rectangle"""
    logger.trace("Rotating landmarks: (rotation_matrix: %s, type(face): %s",
                 rotation_matrix, type(face))
    if isinstance(face, DetectedFace):
        bounding_box = [[face.x, face.y],
                        [face.x + face.w, face.y],
                        [face.x + face.w, face.y + face.h],
                        [face.x, face.y + face.h]]
        landmarks = face.landmarksXY

    elif isinstance(face, dict):
        bounding_box = [[face.get("x", 0), face.get("y", 0)],
                        [face.get("x", 0) + face.get("w", 0),
                         face.get("y", 0)],
                        [face.get("x", 0) + face.get("w", 0),
                         face.get("y", 0) + face.get("h", 0)],
                        [face.get("x", 0),
                         face.get("y", 0) + face.get("h", 0)]]
        landmarks = face.get("landmarksXY", list())

    elif isinstance(face,
                    dlib.rectangle):  # pylint: disable=c-extension-no-member
        bounding_box = [[face.left(), face.top()],
                        [face.right(), face.top()],
                        [face.right(), face.bottom()],
                        [face.left(), face.bottom()]]
        landmarks = list()
    else:
        raise ValueError("Unsupported face type")

    logger.trace("Original landmarks: %s", landmarks)

    rotation_matrix = cv2.invertAffineTransform(  # pylint: disable=no-member
        rotation_matrix)
    rotated = list()
    for item in (bounding_box, landmarks):
        if not item:
            continue
        points = np.array(item, np.int32)
        points = np.expand_dims(points, axis=0)
        transformed = cv2.transform(points,  # pylint: disable=no-member
                                    rotation_matrix).astype(np.int32)
        rotated.append(transformed.squeeze())

    # Bounding box should follow x, y planes, so get min/max
    # for non-90 degree rotations
    pt_x = min([pnt[0] for pnt in rotated[0]])
    pt_y = min([pnt[1] for pnt in rotated[0]])
    pt_x1 = max([pnt[0] for pnt in rotated[0]])
    pt_y1 = max([pnt[1] for pnt in rotated[0]])

    if isinstance(face, DetectedFace):
        face.x = int(pt_x)
        face.y = int(pt_y)
        face.w = int(pt_x1 - pt_x)
        face.h = int(pt_y1 - pt_y)
        face.r = 0
        if len(rotated) > 1:
            rotated_landmarks = [tuple(point) for point in rotated[1].tolist()]
            face.landmarksXY = rotated_landmarks
    elif isinstance(face, dict):
        face["x"] = int(pt_x)
        face["y"] = int(pt_y)
        face["w"] = int(pt_x1 - pt_x)
        face["h"] = int(pt_y1 - pt_y)
        face["r"] = 0
        if len(rotated) > 1:
            rotated_landmarks = [tuple(point) for point in rotated[1].tolist()]
            face["landmarksXY"] = rotated_landmarks
    else:
        rotated_landmarks = dlib.rectangle(  # pylint: disable=c-extension-no-member
            int(pt_x), int(pt_y), int(pt_x1), int(pt_y1))
        face = rotated_landmarks

    logger.trace("Rotated landmarks: %s", rotated_landmarks)
    return face


def camel_case_split(identifier):
    """ Split a camel case name
        from: https://stackoverflow.com/questions/29916065 """
    matches = finditer(
        ".+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)",
        identifier)
    return [m.group(0) for m in matches]


def safe_shutdown():
    """ Close queues, threads and processes in event of crash """
    logger.debug("Safely shutting down")
    from lib.queue_manager import queue_manager
    from lib.multithreading import terminate_processes
    queue_manager.terminate_queues()
    terminate_processes()
    logger.debug("Cleanup complete. Shutting down queue manager and exiting")
    queue_manager._log_queue.put(None)  # pylint: disable=protected-access
    while not queue_manager._log_queue.empty():  # pylint: disable=protected-access
        continue
    queue_manager.manager.shutdown()

def parse_model_weights(self, weight_file, model_file):

    # handles grouped convolutions
    def convolution(weights_dict, name, input, group, conv_type, filters=None, **kwargs):
        if not conv_type.startswith('layer'):
            layer = keras.applications.mobilenet.DepthwiseConv2D(name=name,
                                                                 **kwargs)(input)
            return layer
            
        if group == 1:
            func = getattr(layers, conv_type.split('.')[-1])
            layer = func(name = name, filters = filters, **kwargs)(input)
            return layer
            
        group_list = []
        weight_groups = []
        if not weights_dict == None:
            w = numpy.array(weights_dict[name]['weights'])
            weight_groups = numpy.split(w, indices_or_sections=group, axis=-1)
            
        grouped_channels = int(filters / group)
        for c in range(group):
            x = layers.Lambda(lambda z: z[:, :, :, c * grouped_channels:(c + 1) * grouped_channels])(input)
            x = layers.Conv2D(name=name + "_" + str(c), filters=grouped_channels, **kwargs)(x)
            weights_dict[name + "_" + str(c)] = dict()
            weights_dict[name + "_" + str(c)]['weights'] = weight_groups[c]
            group_list.append(x)
            
        layer = layers.concatenate(group_list, axis = -1)
        
        if 'bias' in weights_dict[name]:
            b = K.variable(weights_dict[name]['bias'], name = name + "_bias")
            layer = layer + b
            
        return layer
        
    def load_weights_from_file(weight_file):
        try:
            weights_dict = numpy.load(weight_file).item()
        except:
            weights_dict = numpy.load(weight_file, encoding='bytes').item()
            
        return weights_dict
        
    def set_layer_weights(model, weights_dict):
        for layer in model.layers:
            if layer.name in weights_dict:
                cur_dict = weights_dict[layer.name]
                current_layer_parameters = []
                
                if layer.__class__.__name__ == "BatchNormalization":
                    if 'scale' in cur_dict:
                        current_layer_parameters.append(cur_dict['scale'])
                    if 'bias' in cur_dict:
                        current_layer_parameters.append(cur_dict['bias'])
                    current_layer_parameters.extend([cur_dict['mean'],
                                                    cur_dict['var']])
                                                    
                elif layer.__class__.__name__ == "Scale":
                    if 'scale' in cur_dict:
                        current_layer_parameters.append(cur_dict['scale'])
                    if 'bias' in cur_dict:
                        current_layer_parameters.append(cur_dict['bias'])
                        
                elif layer.__class__.__name__ == "SeparableConv2D":
                    current_layer_parameters = [cur_dict['depthwise_filter'],
                                                cur_dict['pointwise_filter']]
                    if 'bias' in cur_dict:
                        current_layer_parameters.append(cur_dict['bias'])
                        
                else:
                    current_layer_parameters = [cur_dict['weights']]
                    if 'bias' in cur_dict:
                        current_layer_parameters.append(cur_dict['bias'])
                        
                model.get_layer(layer.name).set_weights(current_layer_parameters)
                
        return model

    weights_dict = load_weights_from_file(weight_file)
    
    input        = layers.Input(name = 'input', shape = (300, 300, 3,) )
    input_c      = layers.ZeroPadding2D(padding = ((100, 100), (100, 100)))(input)
    conv1_1      = convolution(weights_dict, name='conv1_1', input=input_c, group=1, conv_type='layers.Conv2D', filters=64, kernel_size=(3, 3), activation='relu')
    conv1_2      = convolution(weights_dict, name='conv1_2', input=conv1_1, group=1, conv_type='layers.Conv2D', filters=64, kernel_size=(3, 3), activation='relu', padding='same')
    pool1        = layers.MaxPooling2D(name = 'pool1', pool_size = (2, 2), strides = (2, 2), padding='same')(conv1_2)
    
    conv2_1      = convolution(weights_dict, name='conv2_1', input=pool1, group=1, conv_type='layers.Conv2D', filters=128, kernel_size=(3, 3), activation='relu', padding='same')
    conv2_2      = convolution(weights_dict, name='conv2_2', input=conv2_1, group=1, conv_type='layers.Conv2D', filters=128, kernel_size=(3, 3), activation='relu', padding='same')
    pool2        = layers.MaxPooling2D(name = 'pool2', pool_size = (2, 2), strides = (2, 2), padding='same')(conv2_2)
    
    conv3_1      = convolution(weights_dict, name='conv3_1', input=pool2, group=1, conv_type='layers.Conv2D', filters=256, kernel_size=(3, 3), activation='relu', padding='same')
    conv3_2      = convolution(weights_dict, name='conv3_2', input=conv3_1, group=1, conv_type='layers.Conv2D', filters=256, kernel_size=(3, 3), activation='relu', padding='same')
    conv3_3      = convolution(weights_dict, name='conv3_3', input=conv3_2, group=1, conv_type='layers.Conv2D', filters=256, kernel_size=(3, 3), activation='relu', padding='same')
    pool3        = layers.MaxPooling2D(name = 'pool3', pool_size = (2, 2), strides = (2, 2), padding='same')(conv3_3)
    
    conv4_1      = convolution(weights_dict, name='conv4_1', input=pool3, group=1, conv_type='layers.Conv2D', filters=512, kernel_size=(3, 3), activation='relu', padding='same')
    conv4_2      = convolution(weights_dict, name='conv4_2', input=conv4_1, group=1, conv_type='layers.Conv2D', filters=512, kernel_size=(3, 3), activation='relu', padding='same')
    conv4_3      = convolution(weights_dict, name='conv4_3', input=conv4_2, group=1, conv_type='layers.Conv2D', filters=512, kernel_size=(3, 3), activation='relu', padding='same')
    pool4        = layers.MaxPooling2D(name = 'pool4', pool_size = (2, 2), strides = (2, 2), padding='same')(conv4_3)
    
    conv5_1      = convolution(weights_dict, name='conv5_1', input=pool4, group=1, conv_type='layers.Conv2D', filters=512, kernel_size=(3, 3), activation='relu', padding='same')
    conv5_2      = convolution(weights_dict, name='conv5_2', input=conv5_1, group=1, conv_type='layers.Conv2D', filters=512, kernel_size=(3, 3), activation='relu', padding='same')
    conv5_3      = convolution(weights_dict, name='conv5_3', input=conv5_2, group=1, conv_type='layers.Conv2D', filters=512, kernel_size=(3, 3), activation='relu', padding='same')
    pool5        = layers.MaxPooling2D(name = 'pool5', pool_size = (2, 2), strides = (2, 2), padding='same')(conv5_3)
    
    fc6          = convolution(weights_dict, name='fc6', input=pool5, group=1, conv_type='layers.Conv2D', filters=4096, kernel_size=(7, 7), activation='relu')
    drop6        = layers.Dropout(name = 'drop6', rate = 0.5, seed = None)(fc6)
    fc7          = convolution(weights_dict, name='fc7', input=drop6, group=1, conv_type='layers.Conv2D', filters=4096, kernel_size=(1, 1), activation='relu')
    drop7        = layers.Dropout(name = 'drop7', rate = 0.5, seed = None)(fc7)
    
    scale_pool3  = layers.Lambda(lambda x: x * 0.0001, name='scale_pool3')(pool3)
    scale_pool4  = layers.Lambda(lambda x: x * 0.01, name='scale_pool4')(pool4)
    score_pool3_r  = convolution(weights_dict, name='score_pool3_r', input=scale_pool3, group=1, conv_type='layers.Conv2D', filters=2, kernel_size=(1, 1))
    score_pool4_r  = convolution(weights_dict, name='score_pool4_r', input=scale_pool4, group=1, conv_type='layers.Conv2D', filters=2, kernel_size=(1, 1))
    score_pool3c = layers.Cropping2D(cropping=((9, 8), (9, 8)), name='score_pool3c')(score_pool3_r)
    score_pool4c = layers.Cropping2D(cropping=((5, 5), (5, 5)), name='score_pool4c')(score_pool4_r)
    
    score_fr_r     = convolution(weights_dict, name='score_fr_r', input=drop7, group=1, conv_type='layers.Conv2D', filters=2, kernel_size=(1, 1))
    upscore2_r   = convolution(weights_dict, name='upscore2_r', input=score_fr_r, group=1, conv_type='layers.Conv2DTranspose', filters=2, kernel_size=(4, 4), strides=(2, 2), use_bias=False)
    fuse_pool4   = layers.add(name = 'fuse_pool4', inputs = [upscore2_r, score_pool4c])
    
    upscore_pool4_r= convolution(weights_dict, name='upscore_pool4_r', input=fuse_pool4, group=1, conv_type='layers.Conv2DTranspose', filters=2, kernel_size=(4, 4), strides=(2, 2), use_bias=False)
    
    fuse_pool3   = layers.add(name = 'fuse_pool3', inputs = [upscore_pool4_r, score_pool3c])
    upscore8_r     = convolution(weights_dict, name='upscore8_r', input=fuse_pool3, group=1, conv_type='layers.Conv2DTranspose', filters=2, kernel_size=(16, 16), strides=(8, 8), use_bias=False)
    score        = layers.Cropping2D(cropping=((31, 45), (31, 45)), name='score')(upscore8_r)
    
    model        = Model(inputs = [input], outputs = [score], name = 'face_seg_fcn_vgg16')
    
    set_layer_weights(model, weights_dict)
    model.save(model_file)
    
    return model
