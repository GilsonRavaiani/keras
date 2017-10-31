from ..utils.data_utils import get_file
import numpy as np


def load_data(path='boston_housing.npz', test_split=0.2, seed=113):
    """Loads the Boston Housing dataset.

    # Arguments
        path: path where to cache the dataset locally
            (relative to ~/.keras/datasets).
        test_split: fraction of the data to reserve as test set.
        seed: Random seed for shuffling the data
            before computing the test split.

    # Returns
        Tuple of Numpy arrays: `(x_train, y_train), (x_test, y_test)`.
    """
    assert 0 <= test_split < 1
    path = get_file(path,
                    origin='https://s3.amazonaws.com/keras-datasets/boston_housing.npz',
                    file_hash='f553886a1f8d56431e820c5b82552d9d95cfcb96d1e678153f8839538947dff5')
    with np.load(path) as f:
        x, y = f['x'], f['y']

    np.random.seed(seed)
    indices = np.arange(len(x))
    np.random.shuffle(indices)
    x, y = x[indices], y[indices]

    idx = int(len(x) * (1 - test_split))
    x_train, y_train = np.array(x[:idx]), np.array(y[:idx])
    x_test, y_test = np.array(x[idx:]), np.array(y[idx:])
    return (x_train, y_train), (x_test, y_test)
