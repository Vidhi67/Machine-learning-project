import os
import shutil
from pathlib import Path
from typing import Tuple, Optional, Union
import keras
import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from tensorflow.data import Dataset
import pandas as pd
from loguru import logger
import enum
from tensorflow.keras.layers import RandomFlip, RandomRotation, RandomZoom, RandomContrast, RandomWidth, RandomHeight
from tensorflow.keras.models import Sequential


class DatasetSplit(enum.Enum):
    TRAIN = 1
    VALIDATION = 2
    TEST = 3
    TRAIN_AND_VALIDATION = 4


def load_and_preprocess_image(*args, **kwargs) -> Tuple[Union[np.ndarray, float], int]:
    """
    Loads an image into a :class:`~numpy.ndarray` preprocess it, return the label as an :class:`int`.

    .. todo:: Add preprocessing logic here. Convert to grayscale, downsample, etc.

    Args:
        *args: Variable length argument list. The inputs depend on the :class:`~pandas.DataFrame` object (or
          :class:`~pandas.Series`) that the :meth:`~pandas.DataFrame.apply` method is called on.
        **kwargs: Arbitrary keyword arguments. The inputs depend on the :class:`~pandas.DataFrame` object (or
          :class:`~pandas.Series`) that the :meth:`~pandas.DataFrame.apply` method is called on.

    Within Args:
        color_mode:
        target_size:
        interpolation:
        keep_aspect_ratio:

    Returns:
        Tuple[tf.Tensor, tf.Tensor]: A tuple containing the image and its corresponding label.

    See Also:
        - https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.apply.html#pandas.DataFrame.apply
        - https://keras.io/api/data_loading/image/#loadimg-function

    """
    image_abs_path = args[0][0]
    image_int_label = args[0][1]
    color_mode = args[1][1]
    target_size = args[2][1]
    interpolation = args[3][1]
    keep_aspect_ratio = args[4][1]
    # logger.debug(f"load_img: {image_abs_path}")
    try:
        image = keras.utils.load_img(
            image_abs_path, color_mode=color_mode, target_size=target_size, interpolation=interpolation,
            keep_aspect_ratio=keep_aspect_ratio
        )
    except Exception as e:
        logger.error(f"Failed to load image: {image_abs_path}")
        logger.error(f"Error: {e}")
        return float('nan'), image_int_label
    image = keras.utils.img_to_array(image)
    return image, image_int_label


def load_datasets(
        color_mode: str, target_size: Optional[Tuple[int, int]], interpolation: str, keep_aspect_ratio: bool,
        num_partitions: int, batch_size: int, oversample_train_set: bool, oversample_val_set: bool, data_aug_train_set: bool,
        num_images: Optional[int] = None, train_set_size: Optional[float] = 0.6, val_set_size: Optional[float] = 0.2,
        test_set_size: Optional[float] = 0.2, seed: Optional[int] = 42, is_multi: Optional[bool] = False,
        num_images_to_upload: Optional[int] = 6) -> [Dataset, Dataset, Dataset, Dataset]:
    """
    Constructs TensorFlow train, val, test :class:`~tensorflow.data.Dataset` s from the provided high resolution image
    training set.

    Args:
        color_mode (str): One of "grayscale", "rgb", "rgba". Default: "rgb". The desired image format.
        target_size (Optional[Tuple[int, int]]): Either ``None`` (default to original size) or tuple of ints
          ``(img_height, img_width)``.
        interpolation (str): Interpolation method used to resample the image if the target size is different from that
          of the loaded image. Supported methods are "nearest", "bilinear", and "bicubic". If PIL version 1.1.3 or newer
          is installed, "lanczos" is also supported. If PIL version 3.4.0 or newer is installed, "box" and "hamming" are
          also supported. By default, "nearest" is used.
        keep_aspect_ratio (bool): Boolean, whether to resize images to a target size without aspect ratio distortion.
          The image is cropped in the center with target aspect ratio before resizing.
        num_partitions (int): An integer value representing the number of partitioned training sets to load in. The
          maximum value is ``6`` (Train_0 - Train_5), the minimum value is ``1`` (Train_0 only).
        batch_size (int): The batch size to use for the training, validation, and testing datasets.
        oversample_train_set (bool): A boolean flag indicating if the training set should be oversampled from the least
          prominent class such that 50% of examples in each batch belong to the positive class and 50% belong to the
          negative class. Note that this assumes a binary classification problem.
        oversample_val_set (bool): A boolean flag indicating if the validation set should be oversampled from the least
          prominent class such that 50% of examples in each batch belong to the positive class and 50% belong to the
          negative class. Note that this assumes a binary classification problem.
        num_images (Optional[int]): The exact number of images to load from the training set. This value takes
          precedence over the specified number of partitions. However, if both ``num_partitions`` and ``num_images`` are
          specified then at most ``num_images`` will be loaded from the subset of partitions specified by
          ``num_partitions``, in other words the other partitions beyond the provided number will be untouched for
          data loading. This value is mostly useful for debugging downstream pipelines, and it defaults to :class:`None`
          indicating that all images in the partitions specified by ``num_partitions`` will be loaded.
        train_set_size (Optional[float]): The percentage of the data to use as the training dataset. This value defaults
          to ``0.6`` (e.g. ``60%``).
        val_set_size (Optional[float]): The percentage of the data to use as the validation dataset. This value defaults
          to ``0.2`` (e.g. ``20%``).
        test_set_size (Optional[float]): The percentage of the data to use as the testing dataset. This value defaults
          to ``0.2`` (e.g. ``20%``).
        seed (Optional[int]): The random seed used to shuffle the data and split the dataset into training, validation,
          and testing sets. This value defaults to ``42``.
        is_multi (Optinal[bool]): Flag used to determine if dataset is for binary classification or multiclass.
          This defaults to ``false``.
    Returns:
        Tuple[:class:`~tensorflow.data.Dataset`, :class:`~tensorflow.data.Dataset`, :class:`~tensorflow.data.Dataset`]:
          A tuple containing the training, validation, and testing datasets.

    """
    if is_multi:
        if oversample_train_set or oversample_val_set:
            raise NotImplementedError(f"Oversampling is not supported for multi-class classification.")
    data_root_dir = os.path.abspath('/usr/local/data/JustRAIGS/')
    # Check if this data has already been loaded and saved to disk:
    dirname_from_args = (f"{color_mode}_{target_size[0]}_{target_size[1]}_{interpolation}_{keep_aspect_ratio}_"
                         f"{num_partitions}_{num_images}_{train_set_size}_{val_set_size}_"
                         f"{test_set_size}_{seed}_{is_multi}")
    dirname_from_args = dirname_from_args.replace('.', '_')
    dirname_from_args = os.path.join(data_root_dir, 'interpolated', dirname_from_args)
    train_dir_from_args = os.path.join(dirname_from_args, 'train')
    val_dir_from_args = os.path.join(dirname_from_args, 'val')
    test_dir_from_args = os.path.join(dirname_from_args, 'test')
    if os.path.isdir(train_dir_from_args) and os.path.isdir(val_dir_from_args) and os.path.isdir(test_dir_from_args):
        logger.debug(f"Found existing saved dataset for the specified arguments! Loading tf.Datasets from: {dirname_from_args}.")
        train_ds = tf.data.Dataset.load(train_dir_from_args)
        val_ds = tf.data.Dataset.load(val_dir_from_args)
        test_ds = tf.data.Dataset.load(test_dir_from_args)
    else:
        logger.debug("No saved datasets found, loading in the data from scratch.")
        high_res_train_data_path = os.path.join(data_root_dir, 'raw', 'train')
        train_data_labels_csv_path = os.path.abspath(os.path.join(high_res_train_data_path, 'JustRAIGS_Train_labels.csv'))
        assert os.path.isfile(train_data_labels_csv_path), f"Failed to find {train_data_labels_csv_path}"
        train_data_labels_df = pd.read_csv(filepath_or_buffer=train_data_labels_csv_path, delimiter=';')
        train_image_abs_file_paths = []
        image_paths_df = pd.DataFrame()
        assert num_partitions <= 6, f"num_partitions must be less than or equal to 6, got {num_partitions}"
        assert num_partitions > 0, f"num_partitions must be greater than 0, got {num_partitions}"
        reached_image_count = False
        for i in range(num_partitions):
            train_set_partition_abs_path = os.path.join(high_res_train_data_path, f"{i}")
            if reached_image_count:
                break
            for root, dirs, files in os.walk(train_set_partition_abs_path):
                if reached_image_count:
                    break
                for file_id, file in enumerate(files):
                    if num_images is not None:
                        if file_id == num_images:
                            reached_image_count = True
                            break
                    train_image_abs_file_path = os.path.join(root, file)
                    train_image_abs_file_paths.append(os.path.join(root, file))
                    image_paths_df = image_paths_df.append(
                        {
                            'AbsPath': train_image_abs_file_path,
                            'Eye ID': file.split('.')[0]
                        }, ignore_index=True
                    )
        # Modify the DataFrame to contain the absolute path to the 'Eye ID' training image:
        train_data_labels_df = train_data_labels_df.merge(image_paths_df, on=['Eye ID'], how='outer')
        del image_paths_df
        if not is_multi:
            # Convert 'NRG' = 0 and 'RG' = 1
            final_label_int_mask = train_data_labels_df['Final Label'] == 'NRG'
            train_data_labels_df['Class Label'] = np.where(final_label_int_mask, 0, 1)
        else:
            train_data_labels_df = train_data_labels_df[train_data_labels_df['Final Label'] == "RG"]
            logger.debug(f"train_data_labels_df num elements where \'Final Label\' == RG: {train_data_labels_df.shape[0]}")
            # Filtering by both graders agreeing on all of the additional labels signifigantly reduces the size
            # of the dataset to aprox. 186. Additionaly, G3 only grades when G1 and G2 dissagree on the final label
            # (NRG vs RG).
            # Get a subset of the DataFrame that contains G1's annotations for the ten classes:
            g1_multilabel_cols = train_data_labels_df.columns[train_data_labels_df.columns.str.startswith('G1')]
            # Subset of the DataFrame that contains G2's annotations for the ten classes:
            g2_multilabel_cols = train_data_labels_df.columns[train_data_labels_df.columns.str.startswith('G2')]
            # Apparently NaN's are themselves "truthy": bool(np.nan) == True. Let's just drop them:
            train_data_labels_df.dropna(inplace=True, axis=0, subset=list(g1_multilabel_cols) + list(g2_multilabel_cols))
            logger.debug(f"train_data_labels_df num elements after dropping NaN's: {train_data_labels_df.shape[0]}")
            g1_multilabel_df = train_data_labels_df[g1_multilabel_cols]
            g2_multilabel_df = train_data_labels_df[g2_multilabel_cols]
            # A mapping of column names from the G2 column names to the G1 column names:
            col_map = {g2_multilabel_col: g1_multilabel_col for g1_multilabel_col, g2_multilabel_col in zip(g1_multilabel_cols, g2_multilabel_cols)}
            # Since the NaN's have been dropped it is safe to typecast the DataFrames to boolean:
            g1_multilabel_df = g1_multilabel_df.astype(bool)
            g2_multilabel_df = g2_multilabel_df.rename(columns=col_map).astype(bool)
            # Bitwise OR between true and false G1 and G2 labels:
            multihot = g1_multilabel_df | g2_multilabel_df.rename(columns=col_map)
            # Drop the G1 from the column names as this is now a boolean OR between G1 and G2:
            multihot = multihot.rename(columns={g1_multilabel_col: g1_multilabel_col.replace('G1 ', '') for g1_multilabel_col in g1_multilabel_cols})
            # count number of disagreements across the ten classes for each sample:
            diff = g1_multilabel_df.compare(g2_multilabel_df.rename(columns=col_map), keep_equal=False)
            # subtract .1 for each disagreement:
            train_data_labels_df["disagreements"] = diff.sum(axis=1) * 0.1
            train_data_labels_df["Sample Weights"] = 1
            train_data_labels_df["Sample Weights"] -= train_data_labels_df["disagreements"]
            # Take the multihot dataframe and convert it to a new column 'Class Label' of a list of boolean arrays:
            train_data_labels_df["Class Label"] = multihot.to_numpy().tolist()


            # diff = g1_multilabel_df.diff(g2_multilabel_df)
            # raise NotImplementedError("Here is where I left off refactoring with pandas-safe operations that aren't modifying a copy of a slice.")

            # train_data_labels_df["multihotG1"] = train_data_labels_df.filter(regex="G1 .*").to_numpy().tolist()
            # train_data_labels_df["multihotG2"] = train_data_labels_df.filter(regex="G2 .*").to_numpy().tolist()
            # train_data_labels_df = train_data_labels_df.query("multihotG1 == multihotG2")
            # train_data_labels_df["multihotG1"] = train_data_labels_df.filter(regex="G1 .*").to_numpy().tolist()
            # train_data_labels_df["multihotG2"] = train_data_labels_df.filter(regex="G2 .*").to_numpy().tolist()
            # multihot_g1 = train_data_labels_df.filter(regex="G1 .*").to_numpy().tolist()
            # multihot_g2 = train_data_labels_df.filter(regex="G2 .*").to_numpy().tolist()
            # # Then we make a "multihot" column that is the element-wise logical OR of the two graders' labels.
            # train_data_labels_df["multihotG1"] = [np.array(x, dtype=bool) for x in train_data_labels_df["multihotG1"]]
            # train_data_labels_df["multihotG2"] = [np.array(x, dtype=bool) for x in train_data_labels_df["multihotG2"]]
            # train_data_labels_df["multihot"] = \
            #     [np.logical_or(g1, g2) for g1, g2 in
            #      zip(train_data_labels_df["multihotG1"], train_data_labels_df["multihotG2"])]
            # # We also need sample weights that subtracts .05 from the weight of each sample if the two graders disagree.
            # train_data_labels_df["Sample Weights"] = [1] * train_data_labels_df.shape[0]
            # # count number of disagreements across the ten classes for each sample
            # train_data_labels_df["disagreements"] = \
            #     [np.sum(np.logical_xor(g1, g2)) for g1, g2 in
            #      zip(train_data_labels_df["multihotG1"], train_data_labels_df["multihotG2"])]
            # # subtract .1 for each disagreement
            # train_data_labels_df["Sample Weights"] -= train_data_labels_df["disagreements"] * 0.1
            # train_data_labels_df = train_data_labels_df.rename(columns={"multihot": "Class Label"})
            # train_data_labels_df = train_data_labels_df.rename(columns={"multihotG1": "Class Label"})
        # # Convert 'NRG' = 0 and 'RG' = 1
        # final_label_int_mask = train_data_labels_df['Final Label'] == 'NRG'
        # train_data_labels_df['Final Label Int'] = np.where(final_label_int_mask, 0, 1)
        # Drop rows with NaN absolute file paths:
        train_data_labels_df = train_data_labels_df[train_data_labels_df['AbsPath'].notna()]
        # Train, Validation, and Testing set partitioning:
        train_ds_df, val_ds_df = train_test_split(
            train_data_labels_df, train_size=train_set_size, test_size=val_set_size + test_set_size,
            shuffle=True, random_state=seed
        )
        logger.debug(f"train_ds_df.shape: {train_ds_df.shape}")
        val_ds_df, test_ds_df = train_test_split(
            val_ds_df, train_size=0.5, test_size=0.5, shuffle=False
        )
        logger.debug(f"val_ds_df.shape: {val_ds_df.shape}")
        logger.debug(f"test_ds_df.shape: {test_ds_df.shape}")
        '''
        At this point we have the dataframes partitioned into train, validation, and testing sets.
        Now we need to convert them to TensorFlow Datasets:
        '''
        train_img_and_labels_df = train_ds_df[['AbsPath', 'Class Label']].apply(
            load_and_preprocess_image, axis=1, raw=True, result_type='reduce', args=(
                ('color_mode', color_mode), ('target_size', target_size), ('interpolation', interpolation),
                ('keep_aspect_ratio', keep_aspect_ratio)
            )
        )
        # Images that fail to load will be NaN, so we drop them:
        train_img_and_labels_df = train_img_and_labels_df.dropna()
        train_img_and_labels_df.rename(columns={'AbsPath': 'NpImage', 'Class Label': 'LabelTensor'}, inplace=True)
        train_ds = tf.data.Dataset.from_tensor_slices(
            (list(train_img_and_labels_df['NpImage']), list(train_img_and_labels_df['LabelTensor']))
        )
        del train_ds_df
        del train_img_and_labels_df
        val_img_and_labels_df = val_ds_df[['AbsPath', 'Class Label']].apply(
            load_and_preprocess_image, axis=1, raw=True, result_type='reduce', args=(
                ('color_mode', color_mode), ('target_size', target_size), ('interpolation', interpolation),
                ('keep_aspect_ratio', keep_aspect_ratio)
            )
        )
        val_img_and_labels_df.rename(columns={'AbsPath': 'NpImage', 'Class Label': 'LabelTensor'}, inplace=True)
        val_img_and_labels_df = val_img_and_labels_df.dropna()
        val_ds = tf.data.Dataset.from_tensor_slices(
            (list(val_img_and_labels_df['NpImage']), list(val_img_and_labels_df['LabelTensor']))
        )
        del val_ds_df
        del val_img_and_labels_df
        test_img_and_labels_df = test_ds_df[['AbsPath', 'Class Label']].apply(
            load_and_preprocess_image, axis=1, raw=True, result_type='reduce', args=(
                ('color_mode', color_mode), ('target_size', target_size), ('interpolation', interpolation),
                ('keep_aspect_ratio', keep_aspect_ratio)
            )
        )
        test_img_and_labels_df.rename(columns={'AbsPath': 'NpImage', 'Class Label': 'LabelTensor'}, inplace=True)
        test_img_and_labels_df = test_img_and_labels_df.dropna()
        test_ds = tf.data.Dataset.from_tensor_slices(
            (list(test_img_and_labels_df['NpImage']), list(test_img_and_labels_df['LabelTensor']))
        )
        del test_ds_df
        del test_img_and_labels_df
        # Save the datasets to disk:
        os.makedirs(train_dir_from_args, exist_ok=True, mode=0o774)
        shutil.chown(train_dir_from_args, group='just_raigs')
        train_ds.save(train_dir_from_args)
        os.makedirs(val_dir_from_args, exist_ok=True, mode=0o774)
        shutil.chown(val_dir_from_args, group='just_raigs')
        val_ds.save(val_dir_from_args)
        os.makedirs(test_dir_from_args, exist_ok=True, mode=0o774)
        shutil.chown(test_dir_from_args, group='just_raigs')
        test_ds.save(test_dir_from_args)

    # Lastly, pull sample num_images_to_upload images from the val set to use with GradCAM. We would like equal number
    # for each class. Return a dataset using tf.data.sample_from_datasets
    # upload_dataset = Dataset.sample_from_datasets(
    #     datasets=[val_ds.filter(lambda x, y: tf.math.equal(y, 1)),
    #               val_ds.filter(lambda x, y: tf.math.equal(y, 0))],
    #     weights=[0.5, 0.5],
    #     seed=seed,
    #     stop_on_empty_dataset=True
    # ).take(num_images_to_upload)
    # logger.debug(f'Cardinality of val_images: {val_images.cardinality().numpy()}')
    # Oversample the training and validation datasets:
    if oversample_train_set:
        logger.debug(f"Oversampling training dataset.")
        train_ds = get_oversampled_dataset(train_ds, batch_size=batch_size, seed=seed)
    if oversample_val_set:
        logger.debug(f"Oversampling validation dataset.")
        val_ds = get_oversampled_dataset(val_ds, batch_size=batch_size, seed=seed)
    if data_aug_train_set:
        logger.debug(f"Data augmentation training dataset.")
        train_ds = get_augmented_dataset(train_ds, batch_size=batch_size, seed=seed)

    '''
    Batch the datasets:
    '''
    # Note: Consider enabling operation determinism if you need to debug something difficult, but this will slow
    # everything down drastically.
    train_ds = train_ds.shuffle(buffer_size=train_ds.cardinality(), seed=seed, reshuffle_each_iteration=False)
    train_ds = train_ds.batch(
        batch_size=batch_size, drop_remainder=True, num_parallel_calls=tf.data.AUTOTUNE, deterministic=False
    )
    val_ds = val_ds.shuffle(buffer_size=val_ds.cardinality(), seed=seed, reshuffle_each_iteration=False)
    val_ds = val_ds.batch(
        batch_size=batch_size, drop_remainder=True, num_parallel_calls=tf.data.AUTOTUNE, deterministic=False
    )
    test_ds = test_ds.shuffle(buffer_size=test_ds.cardinality(), seed=seed, reshuffle_each_iteration=False)
    test_ds = test_ds.batch(
        batch_size=batch_size, drop_remainder=True, num_parallel_calls=tf.data.AUTOTUNE, deterministic=False
    )
    return train_ds, val_ds, test_ds


def get_oversampled_dataset(data: Dataset, batch_size: int, seed: Optional[int] = 250) -> Dataset:
    """
    Oversamples the smaller class of the dataset to balance the class distribution.

    Args:
        data (Dataset): The dataset to oversample.
        batch_size (int): The batch size to use for the oversampled dataset.
        seed (Optional[int]): The random seed used to shuffle the data. This value defaults to ``250``.

    Returns:
        Dataset: The oversampled dataset.
    """
    logger.debug(f"Attempting to oversample the smaller class of the dataset. "
                 f"Cardinality of data: {data.cardinality().numpy()}")

    negative_referral_data = data.filter(lambda x, y: tf.math.equal(y, 0))
    positive_referral_data = data.filter(lambda x, y: tf.math.equal(y, 1))

    pos_len = positive_referral_data.reduce(0, lambda x, _: x + 1).numpy()
    # logger.debug(f"pos_len: {pos_len}")
    neg_len = negative_referral_data.reduce(0, lambda x, _ : x + 1).numpy()
    # logger.debug(f"neg_len: {neg_len}")
    if pos_len == 0 or neg_len == 0:
        logger.warning("One of the classes is empty. No oversampling will be performed.")
        return data
    if pos_len == neg_len:
        logger.warning(f"Dataset already balanced, will not be oversampled again.")
        return data
    logger.debug(f"Cardinality of positive class dataset: {pos_len}")
    logger.debug(f"Cardinality of negative class dataset: {neg_len}")
    shorter_ds = positive_referral_data
    shorter_length = pos_len
    longer_ds = negative_referral_data
    longer_length = neg_len
    if pos_len > neg_len:
        shorter_ds = negative_referral_data
        shorter_length = neg_len
        longer_ds = positive_referral_data
        longer_length = pos_len
    ratio = longer_length / shorter_length
    ratio = int(ratio)
    # logger.debug(f"longer_ds / shorter_ds ratio: {ratio}")
    shorter_repeat = shorter_ds.repeat(ratio)
    # logger.debug(f'New len of shorter_ds: {len(list(shorter_repeat.as_numpy_iterator()))}')
    total_repeat = longer_ds.concatenate(shorter_repeat)
    # total_repeat = total_repeat.shuffle(buffer_size=batch_size, seed=seed, reshuffle_each_iteration=False)
    # total_repeat = tf.data.Dataset.from_tensor_slices(total_repeat)
    num_examples = 0
    num_positive_labels = 0
    num_negative_labels = 0
    for i, (image, image_label) in enumerate(total_repeat):
        num_examples += 1
        if tf.math.equal(image_label, 0):
            # NGR = 0
            num_negative_labels += 1
        elif tf.math.equal(image_label, 1):
            # GR = 1
            num_positive_labels += 1
    logger.debug(f"Cardinality of positive class in oversampled dataset: {num_positive_labels}")
    logger.debug(f"Cardinality of negative class in oversampled dataset: {num_negative_labels}")
    logger.debug(f"Cardinality of oversampled dataset: {num_examples}")
    assert (num_examples == num_negative_labels + num_positive_labels)
    return total_repeat

def get_augmented_dataset(data: Dataset, batch_size: int, seed: Optional[int] = 250) -> Dataset:
    """
    Applies data augmentation to the dataset to increase the diversity of the training data.

    Args:
        data (Dataset): The dataset to augment.
        batch_size (int): The batch size to use for the augmented dataset.
        seed (Optional[int]): The random seed used for shuffling.

    Returns:
        Dataset: The augmented dataset.
    """
    logger.debug(f"Applying data augmentation to the dataset. Cardinality of data: {data.cardinality().numpy()}")

    # Define data augmentation layers
    data_augmentation = tf.keras.Sequential([
        tf.keras.layers.RandomFlip('horizontal_and_vertical'),
        tf.keras.layers.RandomRotation(0.2),
        tf.keras.layers.RandomZoom(0.2),
        tf.keras.layers.RandomContrast(0.2),
        # Add more augmentation techniques as needed
    ])

    def augment(image, label):
        augmented_image = data_augmentation(image)
        return augmented_image, label

    augmented_data = data.map(augment, num_parallel_calls=tf.data.AUTOTUNE)
    augmented_data = augmented_data.shuffle(buffer_size=1000, seed=seed)
    augmented_data = augmented_data.batch(batch_size, drop_remainder=True)
    augmented_data = augmented_data.prefetch(buffer_size=tf.data.AUTOTUNE)

    return augmented_data


if __name__ == '__main__':
    # Note: Change num_partitions to 1 to load in only Train_0, change to 2 to load in Train_0 and Train_1, etc.
    train_ds, val_ds, test_ds = load_datasets(
        color_mode='rgb', target_size=(75, 75), interpolation='bilinear', keep_aspect_ratio=False, num_partitions=6,
        batch_size=128, num_images=3000, train_set_size=0.6, val_set_size=0.2, test_set_size=0.2, seed=42, is_multi=False,
        oversample_train_set=False, oversample_val_set=False, data_aug_train_set=True )

