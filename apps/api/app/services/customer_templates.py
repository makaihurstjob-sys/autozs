from __future__ import annotations

import re
from typing import Any


PLACEHOLDER_PATTERN = re.compile(r"\[\[([a-z0-9_]+)\]\]")


def _template(
    number: int,
    key: str,
    category: str,
    title: str,
    body: str,
    *,
    automation: str = "manual",
    review_note: str = "",
) -> dict[str, Any]:
    placeholders = list(dict.fromkeys(PLACEHOLDER_PATTERN.findall(body)))
    return {
        "number": number,
        "key": key,
        "category": category,
        "title": title,
        "body": body.strip(),
        "placeholders": placeholders,
        "automation": automation,
        "requires_review": automation != "automatic",
        "review_note": review_note,
    }


CUSTOMER_TEMPLATES = [
    _template(
        1,
        "post_sale_thank_you",
        "Post-Sales General",
        "Post-sale thank you",
        """
Hello [[buyer_first_name]],

Thank you for your purchase. I value your business and am doing everything I can to have your parcel delivered quickly and in perfect condition. Tracking will be added to your order as soon as it is available. In the meantime, please message me with any questions about your order.

Thank you again.

Kind regards,
[[seller_first_name]]
        """,
        automation="automatic",
    ),
    _template(
        2,
        "address_problem",
        "Post-Sales General",
        "Trouble shipping to buyer address",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry, but I am having trouble processing the shipping address provided. Could you please confirm the address exactly as it should appear, including any apartment or unit number? If needed, you may provide a different valid shipping address through the appropriate eBay order process.

Please reply soon so I can resolve this as quickly as possible.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm eBay address-change rules before promising shipment to another address.",
    ),
    _template(
        3,
        "feedback_reciprocal",
        "Post-Sales General",
        "Buyer asks for feedback",
        """
Hello [[buyer_first_name]],

Thank you very much for your purchase and positive feedback. I truly appreciate it.

My feedback system is automatic and normally leaves feedback after buyer feedback is received. If you do not see it after the system has had time to update, please contact me again and I will check it.

Thank you for your understanding.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        4,
        "supplier_receipt_price",
        "Post-Sales General",
        "Supplier receipt or invoice price question",
        """
Hello [[buyer_first_name]], and thank you for contacting me.

Some fulfillment packages may include a supplier receipt showing my procurement cost. Your eBay order total is the price shown and accepted on the listing and includes sourcing, marketplace costs, fulfillment, and customer support. If the item is incorrect, damaged, or otherwise not as described, please let me know and I will help through the appropriate eBay return process.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Use a factual explanation only; do not misstate fees, packing, or supplier terms.",
    ),
    _template(
        5,
        "fulfillment_partner_packaging",
        "Post-Sales General",
        "Unexpected fulfillment-partner packaging",
        """
Hello [[buyer_first_name]], and thank you for contacting me.

I am glad your order arrived. I use third-party fulfillment partners to help provide reliable delivery, so a package may carry a partner's branding. Your purchase, support, returns, and any resolution remain connected to your eBay order with me.

Please let me know if the item or delivery has any issue.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm the actual fulfillment source before sending.",
    ),
    _template(
        6,
        "cannot_replace_parts",
        "Post-Sales General",
        "Cannot replace individual parts",
        """
Hello [[buyer_first_name]], and thank you for contacting me.

I am sorry, but I cannot ship individual replacement parts because I only stock the complete item. Would you consider returning the item for a full refund through eBay? If so, please let me know and I will help with the next step.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        7,
        "address_change_already_shipped",
        "Post-Sales General",
        "Address change requested after shipment",
        """
Hello [[buyer_first_name]],

Thank you for your purchase and message. Your order entered the shipping process quickly and is already on its way, so I can no longer revise the address.

Tracking number: [[tracking_number]]
Carrier: [[shipping_carrier]]

You may contact the carrier to ask whether delivery options are available. I appreciate your understanding.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        8,
        "buyer_happy",
        "Post-Sales General",
        "Buyer is happy with purchase",
        """
Hello [[buyer_first_name]],

Thank you so much for the update. I am thrilled to hear the item met your expectations and arrived in good condition.

Thank you again for your purchase.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        9,
        "address_change_accepted",
        "Post-Sales General",
        "Address change accepted",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I have noted the following requested address:

[[new_address]]

Please confirm it is correct. Any address change must also comply with eBay seller-protection requirements before shipment. Tracking will be added once available.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Never send until the new address and eBay seller-protection eligibility are verified.",
    ),
    _template(
        10,
        "refund_issued_after_return",
        "Returns",
        "Refund issued after return",
        """
Hello [[buyer_first_name]],

Thank you for returning the item. The return has been processed and I have submitted the full refund through eBay. Please allow the payment provider's normal processing time for it to appear.

Please contact me if you have any further questions.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Send only after eBay confirms the refund was issued.",
    ),
    _template(
        11,
        "not_as_described_label",
        "Returns",
        "Not as described—prepaid label",
        """
Hello [[buyer_first_name]],

I am very sorry the item was not as described. I take responsibility and will issue a full refund after the return is received or as required by the eBay return case.

Please use the prepaid return label attached through eBay and retain the tracking number. Let me know once it has shipped.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm the label is actually attached in the eBay return case.",
    ),
    _template(
        12,
        "open_ebay_return",
        "Returns",
        "Ask buyer to open an eBay return",
        """
Hello [[buyer_first_name]],

I am sorry the item did not meet your expectations. Please open a return request for the item through eBay so both of us can track the package and I can provide the required return information there.

Thank you for your cooperation.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        13,
        "refund_not_visible",
        "Returns",
        "Buyer cannot see issued refund",
        """
Hello [[buyer_first_name]], and thank you for your message.

I am sorry the refund is not visible yet. eBay shows that the refund was issued on [[refund_date]] with reference [[refund_reference]]. Payment providers can take additional time to post it. Please contact eBay support with that reference if it remains unavailable.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Verify the refund date/reference and redact sensitive payment data before attaching proof.",
    ),
    _template(
        14,
        "carrier_returned_item",
        "Returns",
        "Carrier returned item as undeliverable",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

Unfortunately, the carrier returned your order as undeliverable. I am sorry for the inconvenience.

Would you prefer a refund, or should I check whether reshipment is possible? Please also confirm the shipping address through eBay.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        15,
        "international_shipping_damage",
        "Returns",
        "International shipping damage",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry the item or package arrived damaged. Because this order used eBay's international shipping program, please open a case with eBay and include photos of the package and item. I will also cooperate with any information eBay requests from me.

Please let me know how else I can assist.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm the order actually used eBay International Shipping before sending.",
    ),
    _template(
        16,
        "changed_mind_return_label",
        "Returns",
        "Changed-mind return—label provided",
        """
Hello [[buyer_first_name]], and thank you for contacting me.

I am happy to assist with the return. Please use the return label provided through eBay, retain the tracking number, and let me know when the package has shipped.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm who is responsible for return shipping under the listing policy.",
    ),
    _template(
        17,
        "damaged_return_label",
        "Returns",
        "Damaged item—prepaid label",
        """
Hello [[buyer_first_name]],

I am very sorry the item arrived damaged. Please use the prepaid return label attached through eBay and securely package the item for return. Retain the tracking number and let me know once it ships.

Thank you for your cooperation.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm the prepaid label is available before sending.",
    ),
    _template(
        18,
        "return_window_expired",
        "Returns",
        "Return window expired",
        """
Hello [[buyer_first_name]],

I am sorry you are unhappy with the item. The listing's return window has expired, so I may not be able to accept a standard return. Please tell me what is wrong and I will review what options may still be available under eBay policy and applicable law.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Do not promise discounts or deny statutory/eBay protections without reviewing the case.",
    ),
    _template(
        19,
        "return_tracking_needed",
        "Returns",
        "Request return tracking number",
        """
Hello [[buyer_first_name]],

Thank you for shipping the item back. Could you please provide the return tracking number so I can locate the package and process the next step as quickly as possible?

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        20,
        "ups_pickup_scheduled",
        "Returns",
        "UPS pickup scheduled",
        """
Hello [[buyer_first_name]],

As discussed, a UPS pickup has been scheduled for your return between [[pickup_date_range]].

Please securely pack the item, preferably in its original packaging. The UPS driver should bring the prepaid label. If you will not be available, follow the carrier's instructions for a safe pickup location.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Verify the pickup confirmation and date range before sending.",
    ),
    _template(
        21,
        "when_will_order_ship",
        "Item Delivery",
        "When will my order ship?",
        """
Hello [[buyer_first_name]],

Thank you for your purchase. Your order is being prepared and is currently expected to arrive between [[delivery_date_range]]. Tracking will be added to your eBay order as soon as it is available.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Use only a confirmed delivery estimate.",
    ),
    _template(
        22,
        "shipping_delay_no_tracking",
        "Item Delivery",
        "Shipping delay—no tracking yet",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry for the delay. I am checking the shipment status and will add tracking as soon as it is confirmed. I appreciate your patience and will follow up with a verified update.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        23,
        "lost_offer_replacement",
        "Item Delivery",
        "Shipment appears lost—offer replacement",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am very sorry, but the shipment appears to have been lost in transit. Would you like me to check whether a replacement is available? If it is unavailable, I will help arrange a refund through eBay.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm the carrier investigation/status before declaring a package lost.",
    ),
    _template(
        24,
        "lost_refund_pending",
        "Item Delivery",
        "Shipment lost—refund pending",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am very sorry, but the shipment appears to have been lost in transit. I am reviewing the order and will process the appropriate refund through eBay within [[refund_timeframe]].

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm loss and the promised refund timeframe before sending.",
    ),
    _template(
        25,
        "lost_open_item_not_received",
        "Item Delivery",
        "Shipment lost—open item-not-received request",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry the shipment appears to be lost. Please open an “item not received” request through eBay so the order, tracking, and refund can be handled in the protected eBay workflow.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        26,
        "international_shipping_delay",
        "Item Delivery",
        "International shipping program delay",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry the item has not arrived. Tracking shows it reached eBay's international shipping facility. Please contact eBay support through the order because eBay manages the international leg after that handoff. I will cooperate with any information they request.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm tracking shows the eBay international hub handoff.",
    ),
    _template(
        27,
        "delivered_not_received",
        "Item Delivery",
        "Marked delivered but buyer cannot locate it",
        """
Hello [[buyer_first_name]],

I am sorry you cannot locate the package. [[shipping_carrier]] reports it delivered on [[delivery_date]] under tracking number [[tracking_number]].

Carriers occasionally scan packages shortly before the final handoff. Please allow two business days and check with household members, neighbors, building staff, and the delivery location. If it is still missing after that, reply and I will help with the next step.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Verify carrier, tracking number, and delivery date before sending.",
    ),
    _template(
        28,
        "not_received_investigating",
        "Item Delivery",
        "Item not received—investigating",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry the order has not arrived. I will investigate with the fulfillment partner and carrier and follow up within two business days.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        29,
        "too_late_to_cancel",
        "Cancellations",
        "Too late to cancel",
        """
Hello [[buyer_first_name]],

Thank you for your purchase. The order has already entered the shipping process, so I can no longer cancel it.

If you do not wish to keep the item, please use the eBay return process after delivery. I appreciate your understanding.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Verify the order is actually shipped or irrevocably processing.",
    ),
    _template(
        30,
        "cannot_fulfill_refunded",
        "Cancellations",
        "Cannot fulfill order—refund issued",
        """
Hello [[buyer_first_name]],

Thank you for your purchase. Unfortunately, I cannot ship this item to the destination provided because [[cancellation_reason]].

I am sorry for the inconvenience. The order has been cancelled and fully refunded through eBay.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Send only after the cancellation and refund are confirmed.",
    ),
    _template(
        31,
        "shipping_delay_offer_cancel",
        "Cancellations",
        "Delay before shipment—offer cancellation",
        """
Hello [[buyer_first_name]], and thank you for your purchase.

I am sorry for the shipping delay. The current estimate is [[delivery_date_range]]. I am working to move the order forward, but I can also cancel and refund it if you prefer.

Please let me know which option you would like.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        32,
        "upset_after_cancellation",
        "Cancellations",
        "Buyer upset after cancellation",
        """
Hello [[buyer_first_name]],

I understand your frustration and am sorry the order could not be completed. This was not intentional, and I appreciate the opportunity to explain what happened: [[cancellation_reason]].

If there is a policy-compliant way I can help resolve the issue, please let me know.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Do not condition discounts, refunds, or compensation on feedback.",
    ),
    _template(
        33,
        "out_of_stock",
        "Pre-Sales",
        "Item temporarily out of stock",
        """
Hello, and thank you for your message.

I apologize, but this item is currently out of stock. You may watch the listing for availability updates.

Thank you for your interest.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        34,
        "different_item_unavailable",
        "Pre-Sales",
        "Requested different item is unavailable",
        """
Hello,

Thank you for your interest. Unfortunately, I do not currently have the different item you described; only the item shown in the listing is available.

Please feel free to contact me with other questions.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        35,
        "lower_price_request",
        "Pre-Sales",
        "Request to lower price",
        """
Hello, and thank you for your interest.

The current listing price is the best price I can offer at this time while still providing reliable fulfillment and support.

Thank you for understanding.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        36,
        "is_item_new",
        "Pre-Sales",
        "Is the item new?",
        """
Hello, and thank you for your question.

The listing condition is [[item_condition]]. Please review the listing photos and condition description, and let me know if you need any other details.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Confirm the listing condition before sending.",
    ),
    _template(
        37,
        "details_unknown",
        "Pre-Sales",
        "Product detail not yet confirmed",
        """
Hello, and thank you for your message.

I do not want to guess about that specification. I am checking the product information and will reply when I can confirm it. The listing's return terms will apply if the delivered item is not as described.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        38,
        "general_item_answer",
        "Pre-Sales",
        "General product answer",
        """
Hello, and thank you for your question.

The confirmed information is: [[product_information]]

Please let me know if you have another question.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Use only verified product information.",
    ),
    _template(
        39,
        "carrier_question",
        "Pre-Sales",
        "Which carrier will deliver?",
        """
Hello [[buyer_first_name]], and thank you for your question.

Standard shipping may be delivered by USPS, UPS, FedEx, or another local last-mile carrier. The exact carrier and tracking number will appear on the eBay order once assigned.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        40,
        "expiration_date_unknown",
        "Pre-Sales",
        "Expiration date not confirmed",
        """
Hello, and thank you for your question.

I cannot confirm the exact expiration date of the unit that would ship, so I do not want to provide an inaccurate estimate. If a specific minimum date is required, please wait until I can verify it before ordering.

Kind regards,
[[seller_first_name]]
        """,
    ),
    _template(
        41,
        "vero_removed",
        "Pre-Sales",
        "VeRO notice acknowledged",
        """
Hello, and thank you for your message.

I am sorry for the issue. The listing has been removed while I review the rights-owner concern and make sure it is not relisted without proper authorization.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Send only after the listing is actually removed.",
    ),
    _template(
        42,
        "negative_feedback_resolution",
        "Post-Sales General",
        "Resolve issue after negative feedback",
        """
Hello [[buyer_first_name]],

I am sorry about your experience and would appreciate the opportunity to resolve the underlying issue. Please tell me what outcome would fairly address the order problem, and I will review the options available through eBay.

If the issue is fully resolved to your satisfaction, you may choose whether to update your feedback, but any refund or resolution is not conditional on doing so.

Kind regards,
[[seller_first_name]]
        """,
        review_note="Never condition compensation, refunds, or service on feedback revision.",
    ),
]

TEMPLATES_BY_KEY = {template["key"]: template for template in CUSTOMER_TEMPLATES}


def list_customer_templates() -> list[dict[str, Any]]:
    return [dict(template) for template in CUSTOMER_TEMPLATES]


def render_customer_template(template_key: str, variables: dict[str, str] | None = None) -> dict[str, Any]:
    template = TEMPLATES_BY_KEY.get(template_key)
    if template is None:
        raise LookupError("Customer-service template not found.")
    values = {str(key): str(value).strip() for key, value in (variables or {}).items()}
    body = template["body"]
    for placeholder in template["placeholders"]:
        value = values.get(placeholder, "")
        if value:
            body = body.replace(f"[[{placeholder}]]", value)
    unresolved = PLACEHOLDER_PATTERN.findall(body)
    return {
        **dict(template),
        "rendered_body": body,
        "unresolved_placeholders": list(dict.fromkeys(unresolved)),
    }
