/**
 * @Author: Saadettin Yasir AKEL <developer>
 * @Date:   2019-01-21T13:42:27+03:00
 * @Email:  yasir@harpiya.com
 * @Project: Harpiya Kurumsal Yönetim Sistemi
 * @Filename: form.js
 * @Last modified by:   developer
 * @Last modified time: 2019-01-21T13:56:29+03:00
 * @License: MIT License. See license.txt
 * @Copyright: Harpiya Yazılım Teknolojileri
 */



frappe.provide("frappe.integration_service")

{% include "templates/includes/integrations/mokapay/process.js" with context %}

frappe.integration_service.mokapay_gateway =  frappe.integration_service.mokapay_gateway.extend({
  form: function(reference_id, display_errors) {
    this._super();
    var base = this;
    $(function() {
      // trigger processing info
      $('#mokapay-process-btn').click(function() {
        var billing_info = base.collect_billing_info();
        var card_info = base.collect_card_info();
        var stored_payment_options = base.collect_stored_payment_info();

        $('#mokapay-payment').fadeOut('fast');
        $('#mokapay-process-btn').fadeOut('fast');
        base.process_card(card_info, billing_info, stored_payment_options, reference_id,
          function(err, result) {
            if ( err ) {
							if ( display_errors && err.errors ) {
								frappe.msgprint(err.errors.join("\n"));
							}
              $('#mokapay-error').text(err.error)
              $('#mokapay-payment').fadeIn('fast');
              $('#mokapay-process-btn').fadeIn('fast');
            } else {
              window.location.href = result.redirect_to;
            }
          })
      })

    })

  }

});
