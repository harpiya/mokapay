# -*- coding: utf-8 -*-
# @Author: Saadettin Yasir AKEL <developer>
# @Date:   2019-01-10T21:42:57+03:00
# @Email:  yasir@harpiya.com
# @Project: Harpiya Kurumsal Yönetim Sistemi
# @Filename: setup.py
# @Last modified by:   developer
# @Last modified time: 2019-01-21T13:52:09+03:00
# @License: MIT License. See license.txt
# @Copyright: Harpiya Yazılım Teknolojileri

from setuptools import setup, find_packages

with open('requirements.txt') as f:
	install_requires = f.read().strip().split('\n')

version = '0.0.1'

setup(
	name='mokapay',
	version=version,
	description='Moka Ödeme Sistemi',
	author='Harpiya Yazılım Teknolojileri',
	author_email='info@harpiya.com',
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
