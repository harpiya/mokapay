/**
 * @Author: Saadettin Yasir AKEL <developer>
 * @Date:   2019-01-21T13:46:24+03:00
 * @Email:  yasir@harpiya.com
 * @Project: Harpiya Kurumsal Yönetim Sistemi
 * @Filename: mokapay_embed.js
 * @Last modified by:   developer
 * @Last modified time: 2019-01-21T13:55:19+03:00
 * @License: MIT License. See license.txt
 * @Copyright: Harpiya Yazılım Teknolojileri
 */



frappe.provide("frappe.gateway_selector")

frappe.gateway_selector.mokapay_embed =  frappe.integration_service.mokapay_gateway.extend({
  _initialized: false,

  /**
   * Called when the form is displayed
   */
  show: function() {
    if ( !this._initialized ) {
      this.form('');
    }

    $('#gateway-selector-continue').text("Submit Payment");
  },

  /**
   * Called when the form is hidden
   */
  hide: function() {
    // form was hidden
  },

  /**
   * Process card. Requires a callback function of the form (err, data).
   *
   * When err is not undefined, the payment processing failed. Err should have
   * information about the error.
   *
   * When data is not undefined, the payment processing was successful. Data
   * should return an object of the form:
   * {
   *    redirect_to: <success url>,
   *    status: <status string from Integration Request doctype>
   * }
   */
  process: function(overrides, callback) {
    var data = Object.assign({}, this.process_data, overrides);
    this._process(data, null, callback);
  },

  getSummary: function() {
    this.collect()

    var stored_payment_label = false;
    if ( this.process_data.mokapay_profile && this.process_data.mokapay_profile.payment_id ) {
      stored_payment_label = $('input[name="authorizednet-stored-payment"]:checked').siblings('.long-text').html();
    }

    return frappe.render(frappe.templates.mokapay_summary, Object.assign({
        store_payments: $('#mokapay_store_payment').is(':checked'),
        stored_payment_label: stored_payment_label
      }, this.process_data));
  }

});
