from setuptools import setup
from setuptools import find_packages


setup(name='Keras',
      version='1.0.8',
      description='Deep Learning for Python',
      author='Francois Chollet',
      author_email='francois.chollet@gmail.com',
      url='https://github.com/fchollet/keras',
      download_url='https://github.com/fchollet/keras/tarball/1.0.8',
      license='MIT',
      install_requires=['theano', 'pyyaml', 'six'],
      extras_require={
          'h5py': ['h5py'],
          'visualize': ['pydot-ng'],
      },
      packages=find_packages())
