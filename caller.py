from twilio.rest import Client

def initiate_call(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    webhook_base_url: str,
):
    client = Client(account_sid, auth_token)

    call = client.calls.create(
        to=to_number,
        from_=from_number,
        url=f"{webhook_base_url}/call/start",
        status_callback=f"{webhook_base_url}/call/status",
        status_callback_event=["completed"],
    )

    print(f"Call initiated: {call.sid}")
    return call.sid