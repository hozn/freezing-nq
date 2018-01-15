import falcon

from freezing.nq.autolog import log
from freezing.nq.config import config
from freezing.nq.publish import ActivityPublisher, Destinations
from stravalib import Client


class WebhookResource:

    def __init__(self, publisher:ActivityPublisher):
        self.publisher = publisher

    def on_get(self, req: falcon.Request, resp: falcon.Response):
        """
        The GET request is used by Strava, when the webhook is initially registered, to validate this endpoint.

        See: http://strava.github.io/api/partner/v3/events/
        """
        client = Client()

        strava_request = {k: req.get_param(k) for k in ('hub.challenge', 'hub.mode', 'hub.verify_token')}

        challenge_response = client.handle_subscription_callback(strava_request,
                                                                 verify_token=config.strava_verify_token)

        resp.media = challenge_response

    def on_post(self, req: falcon.Request, resp: falcon.Response):
        """
        Receives a POSt request from Strava to indicate that an activity has been created or updated.

        We use stravalib to deserialize this (although the structure is pretty trivial).  This will the be published to
        beanstalkd (etc.) for picking up by main processing component.

        Message payload:
                subscription_id = Attribute(six.text_type)
                owner_id = Attribute(six.text_type)
                object_id = Attribute(six.text_type)
                object_type = Attribute(six.text_type)
                aspect_type = Attribute(six.text_type)
                event_time = TimestampAttribute()

        See: http://strava.github.io/api/partner/v3/events/
        """
        client = Client()
        result = client.handle_subscription_update(req.media)

        # We only care about activities
        if result.object_type != 'activity':
            log.info("Ignoring non-activity webhook: {}".format(req.media))
        else:
            dest = Destinations.activity_created if result.aspect_type == 'create' else Destinations.activity_updated
            message = result.to_dict()
            log.info("Publishing activity webhook: {}".format(message))
            self.publisher.publish_message(message, dest=dest)