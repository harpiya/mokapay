# @Author: Saadettin Yasir AKEL <developer>
# @Date:   2019-01-21T13:42:26+03:00
# @Email:  yasir@harpiya.com
# @Project: Harpiya Kurumsal Yönetim Sistemi
# @Filename: desktop.py
# @Last modified by:   developer
# @Last modified time: 2019-01-21T13:54:28+03:00
# @License: MIT License. See license.txt
# @Copyright: Harpiya Yazılım Teknolojileri

from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"module_name": "MokaPay",
			"color": "grey",
			"icon": "octicon octicon-file-directory",
			"type": "module",
			"label": _("Moka Ödeme Sistemi")
		}
	]
