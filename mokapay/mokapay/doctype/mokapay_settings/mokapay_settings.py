# @Author: Saadettin Yasir AKEL <developer>
# @Date:   2019-01-10T21:40:33+03:00
# @Email:  yasir@harpiya.com
# @Project: Harpiya Kurumsal Yönetim Sistemi
# @Filename: mokapay_settings.py
# @Last modified by:   developer
# @Last modified time: 2019-01-22T15:33:54+03:00
# @License: MIT License. See license.txt
# @Copyright: Harpiya Yazılım Teknolojileri


"""
# Integrating Authorize.Net

### 1. Validate Currency Support

Example:

	from frappe.integration_broker.doctype.integration_service.integration_service import get_integration_controller

	controller = get_integration_controller("MokaPay")
	controller().validate_transaction_currency(currency)

### 2. Redirect for payment

Example:

	payment_details = {
		"amount": 600,
		"title": "Payment for bill : 111",
		"description": "payment via cart",
		"reference_doctype": "Payment Request",
		"reference_docname": "PR0001",
		"payer_email": "NuranVerkleij@example.com",
		"payer_name": "Nuran Verkleij",
		"order_id": "111",
		"currency": "USD"
	}

	# redirect the user to this url
	url = controller().get_payment_url(**payment_details)


### 3. On Completion of Payment

Write a method for `on_payment_authorized` in the reference doctype

Example:

	def on_payment_authorized(payment_status):
		# your code to handle callback

##### Note:

payment_status - payment gateway will put payment status on callback.
For authorize.net status parameter is one from: [Completed, Failed]


More Details:
<div class="small">For details on how to get your API credentials, follow this link: <a href="https://support.authorize.net/authkb/index?page=content&id=A405" target="_blank">https://support.authorize.net/authkb/index?page=content&id=A405</a></div>

"""

from __future__ import unicode_literals
import frappe
from frappe import _, _dict
from frappe.utils import get_url, call_hook_method, flt
from frappe.model.document import Document
from frappe.integrations.utils import create_request_log, create_payment_gateway, make_post_request
import json
from datetime import datetime
import urllib.parse

from mokapay.exceptions import MokaResponseError, MokaInvalidError
from mokapay.utils import get_mokapay_user, get_card_accronym, authnet_address, get_contact

def log(*args, **kwargs):
	print("\n".join(args))

class MokaPaySettings(Document):
	service_name = "MokaPay"
	supported_currencies = ["TRY", "EUR", "USD"]
	is_embedable = True

	def validate(self):
		create_payment_gateway("MokaPay")
		call_hook_method("payment_gateway_enabled", gateway=self.service_name)
		if not self.flags.ignore_mandatory:
			self.validate_mokapay_credentails()

	def on_update(self):
		pass

	def get_embed_context(self, context):
		# list countries for billing address form
		context["mokapay_countries"] = frappe.get_list("Country", fields=["country_name", "name"], ignore_permissions=1)
		default_country = frappe.get_value("System Settings", "System Settings", "country")
		default_country_doc = next((x for x in context["mokapay_countries"] if x.name == default_country), None)

		country_idx = context["mokapay_countries"].index(default_country_doc)
		context["mokapay_countries"].pop(country_idx)
		context["mokapay_countries"] = [default_country_doc] + context["mokapay_countries"]

		context["year"] = datetime.today().year

		# get the mokapay user record
		authnet_user = get_mokapay_user()

		if authnet_user:
			context["stored_payments"] = authnet_user.get("stored_payments", [])

	def get_embed_form(self, context={}):

		context.update({
			"source": "templates/includes/integrations/mokapay/embed.html"
		})
		context = _dict(context)

		self.get_embed_context(context)

		return {
			"form": frappe.render_template(context.source, context),
			"style_url": "/assets/css/mokapay_embed.css",
			"script_url": "/assets/js/mokapay_embed.js"
		}

	def validate_mokapay_credentails(self):
		pass

	def validate_transaction_currency(self, currency):
		if currency not in self.supported_currencies:
			frappe.throw(_("Please select another payment method. {0} does not support transactions in currency \"{1}\"").format(self.service_name, currency))

	def build_mokapay_request(self, **kwargs):
		"""Creates an mokapay Request record to keep params off the url"""

		data = {
			"doctype": "MokaPay Request",
			"status": "Issued",
		}
		data.update(kwargs)
		del data["reference_docname"] # have to set it after insert

		request = frappe.get_doc(data)
		request.flags.ignore_permissions = 1
		request.insert()

		# TODO: Why must we save doctype first before setting docname?
		request.reference_docname = kwargs["reference_docname"]
		request.save()
		frappe.db.commit()

		return request

	def get_payment_url(self, **kwargs):
		request = self.build_mokapay_request(**kwargs)
		url = "./integrations/mokapay_checkout/{0}"
		result = get_url(url.format(request.get("name" )))
		return result

	def get_settings(self):
		settings = frappe._dict({
			"DealerCode": self.api_dealer,
			"Username": self.api_username,
			"Password": self.get_password(fieldname="api_password", raise_exception=False),
			"CheckKey": "e9173cf746029f6a4c7d345f6c2f761805bbff08d2a990cd55748378189a2e76"
		})

		return settings

	def process_payment(self):
		# used for feedback about which payment was used
		mokapay_data = {}
		# the current logged in contact
		contact = get_contact()
		# get mokapay user if available
		authnet_user = get_mokapay_user()
		# the cc data available
		data = self.process_data

		# get auth keys
		settings = self.get_settings()
		# fetch redirect info
		redirect_to = data.get("notes", {}).get("redirect_to") or None
		redirect_message = data.get("notes", {}).get("redirect_message") or None

		# uses dummy request doc for unittests as we are only testing processing
		if not data.get("unittest"):
			if data.get("name"):
				request = frappe.get_doc("MokaPay Request", data.get("name"))
			else:
				# Create request from scratch when embeding form on the fly
				#
				# This allows payment processing without having to pre-create
				# a request first.
				#
				# This path expects all the payment request information to be
				# available!!
				#
				# keys expected: ('amount', 'currency', 'order_id', 'title', \
				#                 'description', 'payer_email', 'payer_name', \
				#                 'reference_docname', 'reference_doctype')
				request = self.build_mokapay_request(**{ \
					key: data[key] for key in \
						('amount', 'currency', 'order_id', 'title', \
						 'description', 'payer_email', 'payer_name', \
						 'reference_docname', 'reference_doctype') })

				data["name"] = request.get("name")
		else:
			request = frappe.get_doc({"doctype": "MokaPay Request"})

		request.flags.ignore_permissions = 1

		# set the max log level as per settings
		request.max_log_level(self.log_level)

		try:

			if self.card_info:
				# ensure card fields exist
				required_card_fields = ['CardHolderFullName', 'CardNumber', 'ExpMonth', 'ExpYear', 'CvcNumber']
				for f in required_card_fields:
					if not self.card_info.get(f):
						request.status = "Error"
						return request,	None, "Missing field: %s" % f, {}


			# cache billing fields as per authorize api requirements
			billing = authnet_address(self.billing_info)
			if self.shipping_info:
				shipping = authnet_address(self.shipping_info)
			else:
				shipping = None

			# attempt to find valid email address
			email = self.process_data.get("payer_email")

			if email:
				email = email.split(',')[0]

			if "@" not in email and contact:
				email = contact.get("email_id")

				if "@" not in email:
					if contact and contact.user:
						email = frappe.get_value("User", contact.user, "email_id")

						if "@" not in email:
							log("AUTHNET FAILURE! Bad email: {0}".format(email))
							raise ValueError("There are no valid emails associated with this customer")

			# build transaction data
			transaction_data = {
				"PaymentDealerAuthentication": {
					"DealerCode": self.api_dealer,
					"Username": self.api_username,
					"Password": self.get_password(fieldname="api_password", raise_exception=False),
					"CheckKey": "e9173cf746029f6a4c7d345f6c2f761805bbff08d2a990cd55748378189a2e76"
				},
				"PaymentDealerRequest": {
					"CardHolderFullName": self.card_info.get("CardHolderFullName"),
					"CardNumber": self.card_info.get("CardNumber"),
					"ExpMonth": self.card_info.get("ExpMonth"),
					"ExpYear": self.card_info.get("ExpYear"),
					"CvcNumber": self.card_info.get("CvcNumber"),
					"Amount": flt(self.process_data.get("amount")),
					"Currency": "TL",
					"InstallmentNumber": "1",
					"OtherTrxCode": data["order_id"],
					"IsPreAuth": 0,
					"IsPoolPayment": 0,
					"RedirectUrl": "https://pos.testmoka.com/DealerPayment/PayResult?MyTrxId=1A2B3CD456",
					"RedirectType": 0,
					"Description":self.card_info.get("CardHolderFullName"),
					"ClientIP": frappe.local.request_ip
				}
			}


			name_parts = self.card_info["CardHolderFullName"].split(' ')
			first_name = name_parts[0]
			last_name = " ".join(name_parts[1:])

			# add billing information if available
			if len(billing.keys()):
				transaction_data["BuyerInformation"] = billing
				transaction_data["BuyerInformation"]["BuyerFullName"] = first_name
				transaction_data["BuyerInformation"]["BuyerEmail"] =  email

			# include line items if available
			if self.process_data.get("line_items"):
				transaction_data["line_items"] = self.process_data.get("line_items")

			request.log_action("Requesting Transaction: %s" % \
				json.dumps(transaction_data), "Debug")

			# performt transaction finally
			headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
			result = make_post_request("https://service.testmoka.com/PaymentDealer/DoDirectPaymentThreeD", data=json.dumps(transaction_data), headers=headers)
			request.log_action(json.dumps(result), "Debug")

			# if all went well, record transaction id
			if result.get('Data') != None:
				request.transaction_id = result.get('Data')
				redirect_url = result.get("Data")
				request.status = "Issued"
				request.flags.ignore_permissions = 1

			else:
				request.status = "Error"
				request.flags.ignore_permissions = 1

		except MokaInvalidError as iex:
			# log validation errors
			request.log_action(frappe.get_traceback(), "Error")
			request.status = "Error"
			error_msg = ""
			errors = []

			if iex.children and len(iex.children) > 0:
				for field_error in iex.children:
					print(field_error.asdict())
					for field_name, error in field_error.asdict().iteritems():
						errors.append(error)

			error_msg = "\n".join(errors)

			request.error_msg = error_msg

		except MokaResponseError as ex:
			# log mokapay server response errors
			result = ex.full_response
			request.log_action(json.dumps(result), "Debug")
			request.log_action(str(ex), "Error")
			request.status = "Error"
			request.error_msg = ex.text

			redirect_message = str(ex)
			if result and hasattr(result, 'transaction_response'):
				# if there is extra transaction data, log it
				errors = result.transaction_response.errors
				request.log_action("\n".join([err.error_text for err in errors]), "Error")
				request.log_action(frappe.get_traceback(), "Error")

				request.transaction_id = result.Data
				redirect_message = "Success"

			pass

		except Exception as ex:
			log(frappe.get_traceback())
			# any other errors
			request.log_action(frappe.get_traceback(), "Error")
			request.status = "Error"
			request.error_msg = "[UNEXPECTED ERROR]: {0}".format(ex)
			pass


		# now check if we should store payment information on success
		if request.status in ("Captured", "Authorized") and \
			self.card_info and \
			self.card_info.get("store_payment") and \
			contact:

			try:

				# create customer if authnet_user doesn't exist
				if not authnet_user:
					request.log_action("Creating AUTHNET customer", "Info")

					customer_result = authorize.Customer.from_transaction(request.transaction_id)

					request.log_action("Success", "Debug")

					authnet_user = frappe.get_doc({
						"doctype": "MokaPay Users",
						"mokapay_id": customer_result.customer_id,
						"contact": contact.name
					})

				card_store_info = {
					"CardNumber": self.card_info.get("CardNumber"),
					"ExpMonth": self.card_info.get("ExpMonth"),
					"ExpYear": self.card_info.get("ExpYear"),
					"CvcNumber": self.card_info.get("CvcNumber"),
					"billing": self.billing_info
				}

				request.log_action("Storing Payment Information With AUTHNET", "Info")
				request.log_action(json.dumps(card_store_info), "Debug")

				try:
					card_result = authorize.CreditCard.create(
						authnet_user.get("mokapay_id"), card_store_info)
				except MokaResponseError as ex:
					card_result = ex.full_response
					request.log_action(json.dumps(card_result), "Debug")
					request.log_action(str(ex), "Error")

					try:
						# duplicate payment profile
						if card_result["messages"][0]["message"]["code"] == "E00039":
							request.log_action("Duplicate payment profile, ignore", "Error")
						else:
							raise ex
					except:
						raise ex


				request.log_action("Success: %s" % card_result.payment_id, "Debug")

				address_short = "{0}, {1} {2}".format(
					billing.get("city"),
					billing.get("state"),
					billing.get("pincode"))

				card_label = "{0}{1}".format(
					get_card_accronym(self.card_info.get("CardNumber")), self.card_info.get("CardNumber")[-4:])

				authnet_user.flags.ignore_permissions = 1
				authnet_user.append("stored_payments", {
					"doctype": "MokaPay Stored Payment",
					"short_text": "%s %s" % (card_label,
					address_short),
					"long_text": "{0}\n{1}\n{2}, {3} {4}\n{5}".format(
						card_label,
						billing.get("address", ""),
						billing.get("city", ""),
						billing.get("state", ""),
						billing.get("pincode", ""),
						frappe.get_value("Country",  filters={"name": self.billing_info.get("country")}, fieldname="country_name")
					),
					"address_1": self.billing_info.get("address_1"),
					"address_2": self.billing_info.get("address_2"),
					"expires": "{0}-{1}-01".format(
						self.card_info.get("ExpYear"),
						self.card_info.get("ExpMonth")),
					"city": self.billing_info.get("city"),
					"state": self.billing_info.get("state"),
					"postal_code": self.billing_info.get("pincode"),
					"country": frappe.get_value("Country", self.billing_info.get("country"), fieldname="code"),
					"payment_type": "Card",
					"mokapay_payment_id": card_result.payment_id
				})

				mokapay_data.update({
					"customer_id": authnet_user.get("mokapay_id"),
					"payment_id": card_result.payment_id
				})


				if not data.get("unittest"):
					authnet_user.save()

				request.log_action("Stored in DB", "Debug")
			except Exception as exx:
				# any other errors
				request.log_action(frappe.get_traceback(), "Error")
				raise exx

		return request, redirect_to, redirect_message, mokapay_data

	def create_request(self, data):
		self.process_data = frappe._dict(data)

		# try:
		# remove sensitive info from being entered into db
		self.card_info = self.process_data.get("card_info")
		self.billing_info = self.process_data.get("billing_info")
		self.shipping_info = self.process_data.get("shipping_info")
		redirect_url = ""
		request, redirect_to, redirect_message, mokapay_data = self.process_payment()

		if self.process_data.get('creation'):
			del self.process_data['creation']
		if self.process_data.get('modified'):
			del self.process_data['modified']
		if self.process_data.get('log'):
			del self.process_data['log']

		# sanitize card info
		if self.process_data.get("card_info"):
			self.process_data.card_info["CardNumber"] = "%s%s" % ("X" * \
				 (len(self.process_data.card_info["CardNumber"]) - 4),
				self.process_data["card_info"]["CardNumber"][-4:])

			self.process_data.card_info["CvcNumber"] = "X" * \
				 len(self.process_data.card_info["CvcNumber"])

		if not self.process_data.get("unittest"):
			self.integration_request = create_request_log(self.process_data, "Host", self.service_name)

		if request.get('status') == "Captured":
			status = "Completed"
		elif request.get('status') == "Authorized":
			status = "Authorized"
		else:
			status = "Failed"

		request.log_action(status, "Info")

		# prevents unit test from inserting data on db
		if not self.process_data.get("unittest"):
			self.integration_request.status = status
			self.integration_request.save()
			request.save()

		custom_redirect_to = None
		if status != "Failed":
			try:
				if not self.process_data.get("unittest"):
					custom_redirect_to = frappe.get_doc(
						self.process_data.reference_doctype,
						self.process_data.reference_docname).run_method("on_payment_authorized",
						status)
					request.log_action("Custom Redirect To: %s" % custom_redirect_to, "Info")
			except Exception as ex:
				log(frappe.get_traceback())
				request.log_action(frappe.get_traceback(), "Error")
				raise ex

		if custom_redirect_to:
			redirect_to = custom_redirect_to

		if request.status == "Captured" or request.status == "Authorized":
			redirect_url = "/integrations/payment-success"
			redirect_message = "Continue Shopping"
			success = True
		else:
			redirect_url = "/integrations/payment-failed"
			if request.error_msg:
				redirect_message = "Declined due to:\n" + request.error_msg
			else:
				redirect_message = "Declined"
			success = False

		params = []
		if redirect_to:
			# Fixes issue where system passes a relative url for orders
			if redirect_to == "orders":
				redirect_to = "/orders"

			params.append(urllib.parse.urlencode({"redirect_to": redirect_to}))
		if redirect_message:
			params.append(urllib.parse.urlencode({"redirect_message": redirect_message}))

		if len(params) > 0:
			redirect_url += "?" + "&".join(params)

		if not self.process_data.get("unittest"):
			request.log_action("Redirect To: %s" % redirect_url, "Info")
			request.save()
		else:
			for l in request.log:
				print(l.get("level") + "----------------")
				print(l.get("log"))
				print("")

		self.process_data = {}
		self.card_info = {}
		self.billing_info = {}
		self.shipping_info = {}

		return {
			"redirect_to": redirect_url,
			"error": redirect_message if status == "Failed" else None,
			"status": status,
			"mokapay_data": mokapay_data
		}


		# except Exception:
		#     frappe.log_error(frappe.get_traceback())
		#     return{
		#         "redirect_to": frappe.redirect_to_message(_("Server Error"), _("There was an internal error processing your payment. Please try again later.")),
		#         "status": 401
		#     }

@frappe.whitelist(allow_guest=True)
def process(options, request_name=None):
	data = {}

	# handles string json as well as dict argument
	if isinstance(options, str):
		options = json.loads(options)

	# fixes bug where js null value is casted as a string
	if request_name == 'null':
		request_name = None

	if not options.get("unittest"):
		if request_name:
			request = frappe.get_doc("MokaPay Request", request_name).as_dict()
		else:
			request = {}
	else:
		request = {}

	data.update(options)
	data.update(request)

	data = frappe.get_doc("MokaPay Settings").create_request(data)

	frappe.db.commit()
	return data

@frappe.whitelist()
def get_service_details():
	return """
		<div>
			<p>    To obtain the API Login ID and Transaction Key:
				<a href="https://support.authorize.net/authkb/index?page=content&id=A405" target="_blank">
					https://support.authorize.net/authkb/index?page=content&id=A405
				</a>
			</p>
			<p> Steps to configure Service:</p>
			<ol>
				<li>
					Log into the Merchant Interface at https://account.authorize.net.
				</li>
				<br>
				<li>
					Click <strong>Account</strong> from the main toolbar.
				</li>
				<br>
				<li>
					Click <strong>Settings</strong> in the main left-side menu.
				</li>
				<br>
				<li>
					Click <strong>API Credentials & Keys.</strong>
				</li>
				<br>
				<li>
					Enter your <strong>Secret Answer.</strong>
				</li>
				<br>
				<li>
					Select <strong>New Transaction Key.</strong>
				</li>
				<br>
				<li>
					Input API Credentials in <a href="/desk#Form/mokapay%20Settings">MokaPay Settings</a>
				</li>
				<br>
			</ol>
			<p>
				<strong>Note:</strong> When obtaining a new Transaction Key, you may choose to disable the old Transaction Key by clicking the box titled, <strong>Disable Old Transaction Key Immediately</strong>. You may want to do this if you suspect your previous Transaction Key is being used fraudulently.
				Click Submit to continue. Your new Transaction Key is displayed.
				If the <strong>Disable Old Transaction Key Immediately</strong> box is not checked, the old Transaction Key will automatically expire in 24 hours. When the box is checked, the Transaction Key expires immediately.
			</p>
			<p>
				Be sure to store the Transaction Key in a very safe place. Do not share it with anyone, as it is used to protect your transactions.
			</p>
			<p>
				The system-generated Transaction Key is similar to a password and is used to authenticate requests submitted to the gateway. If a request cannot be authenticated using the Transaction Key, the request is rejected. You may generate a new Transaction Key as often as needed.
			</p>
		</div>
	"""
