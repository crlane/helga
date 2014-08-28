# -*- coding: utf8 -*-
import re

from mock import Mock, call, patch
from unittest import TestCase

from helga import comm


class FactoryTestCase(TestCase):

    def setUp(self):
        self.factory = comm.Factory()

    def test_build_protocol(self):
        client = self.factory.buildProtocol('address')
        assert client.factory == self.factory

    @patch('helga.comm.settings')
    def test_client_connection_lost_retries(self, settings):
        settings.AUTO_RECONNECT = True
        connector = Mock()
        self.factory.clientConnectionLost(connector, Exception)
        assert connector.connect.called

    @patch('helga.comm.settings')
    def test_client_connection_lost_raises(self, settings):
        settings.AUTO_RECONNECT = False
        connector = Mock()
        self.assertRaises(Exception, self.factory.clientConnectionLost, connector, Exception)

    @patch('helga.comm.reactor')
    def test_client_connection_failed(self, reactor):
        self.factory.clientConnectionFailed(Mock(), reactor)
        assert reactor.stop.called


class ClientTestCase(TestCase):

    def setUp(self):
        self.client = comm.Client()

    def test_parse_nick(self):
        nick = self.client.parse_nick('foo!~foobar@localhost')
        assert nick == 'foo'

    def test_parse_nick_unicode(self):
        nick = self.client.parse_nick(u'☃!~foobar@localhost')
        assert nick == u'☃'

    @patch('helga.comm.irc.IRCClient')
    def test_me_converts_from_unicode(self, irc):
        snowman = u'☃'
        bytes = '\xe2\x98\x83'
        self.client.me('#foo', snowman)
        irc.describe.assert_called_with(self.client, '#foo', bytes)

    @patch('helga.comm.irc.IRCClient')
    def test_msg_sends_byte_string(self, irc):
        snowman = u'☃'
        bytes = '\xe2\x98\x83'

        self.client.msg('#foo', snowman)
        irc.msg.assert_called_with(self.client, '#foo', bytes)

    def test_alterCollidedNick(self):
        self.client.alterCollidedNick('foo')
        assert re.match(r'foo_[\d]+', self.client.nickname)

        # Should take the first part up to '_'
        self.client.alterCollidedNick('foo_bar')
        assert re.match(r'foo_[\d]+', self.client.nickname)

    @patch('helga.comm.settings')
    def test_signedOn(self, settings):
        snowman = u'☃'
        bytes = '\xe2\x98\x83'

        settings.CHANNELS = [
            ('#bots',),
            ('#foo', 'bar'),
            (u'#baz', snowman),  # Handles unicode gracefully?
        ]

        with patch.object(self.client, 'join') as join:
            self.client.signedOn()
            assert join.call_args_list == [
                call('#bots'),
                call('#foo', 'bar'),
                call('#baz', bytes),
            ]

    @patch('helga.comm.settings')
    @patch('helga.comm.smokesignal')
    def test_signedOn_sends_signal(self, signal, settings):
        settings.CHANNELS = []
        self.client.signedOn()
        signal.emit.assert_called_with('signon', self.client)

    @patch('helga.comm.registry')
    def test_privmsg_sends_single_string(self, registry):
        self.client.msg = Mock()
        registry.process.return_value = ['line1', 'line2']

        self.client.privmsg('foo!~bar@baz', '#bots', 'this is the input')

        args = self.client.msg.call_args[0]
        assert args[0] == '#bots'
        assert args[1] == 'line1\nline2'

    @patch('helga.comm.registry')
    def test_privmsg_responds_to_user_when_private(self, registry):
        self.client.nickname = 'helga'
        self.client.msg = Mock()
        registry.process.return_value = ['line1', 'line2']

        self.client.privmsg('foo!~bar@baz', 'helga', 'this is the input')

        assert self.client.msg.call_args[0][0] == 'foo'

    @patch('helga.comm.settings')
    @patch('helga.comm.irc.IRCClient')
    def test_connectionMade(self, irc, settings):
        self.client.connectionMade()
        irc.connectionMade.assert_called_with(self.client)

    @patch('helga.comm.settings')
    @patch('helga.comm.irc.IRCClient')
    def test_connectionLost(self, irc, settings):
        self.client.connectionLost('an error...')
        irc.connectionLost.assert_called_with(self.client, 'an error...')

    @patch('helga.comm.settings')
    @patch('helga.comm.irc.IRCClient')
    def test_connectionLost_handles_unicode(self, irc, settings):
        snowman = u'☃'
        bytes = '\xe2\x98\x83'
        self.client.connectionLost(snowman)
        irc.connectionLost.assert_called_with(self.client, bytes)

    @patch('helga.comm.smokesignal')
    def test_joined(self, signal):
        # Test str and unicode
        for channel in ('foo', u'☃'):
            assert channel not in self.client.channels
            self.client.joined(channel)
            assert channel in self.client.channels
            signal.emit.assert_called_with('join', self.client, channel)

    @patch('helga.comm.smokesignal')
    def test_left(self, signal):
        # Test str and unicode
        for channel in ('foo', u'☃'):
            self.client.channels.add(channel)
            self.client.left(channel)
            assert channel not in self.client.channels
            signal.emit.assert_called_with('left', self.client, channel)

    def test_kickedFrom(self):
        # Test str and unicode
        for channel in ('foo', u'☃'):
            self.client.channels.add(channel)
            self.client.kickedFrom(channel, 'me', 'no bots allowed')
            assert channel not in self.client.channels

    def test_on_invite(self):
        with patch.object(self.client, 'join') as join:
            self.client.nickname = 'helga'
            self.client.on_invite('me', 'helga', '#bots')
            assert join.called

    def test_on_invite_ignores_other_invites(self):
        with patch.object(self.client, 'join') as join:
            self.client.nickname = 'helga'
            self.client.on_invite('me', 'someone_else', '#bots')
            assert not join.called

    def test_irc_unknown(self):
        with patch.object(self.client, 'on_invite') as on_invite:
            self.client.irc_unknown('me', 'INVITE', ['helga', '#bots'])
            on_invite.assert_called_with('me', 'helga', '#bots')

            on_invite.reset_mock()
            self.client.irc_unknown('me', 'SOME_COMMAND', [])
            assert not on_invite.called

    @patch('helga.comm.smokesignal')
    def test_userJoined(self, signal):
        user = 'helga!helgabot@127.0.0.1'
        self.client.userJoined(user, '#bots')
        signal.emit.assert_called_with('user_joined', self.client, 'helga', '#bots')

    @patch('helga.comm.smokesignal')
    def test_userLeft(self, signal):
        user = 'helga!helgabot@127.0.0.1'
        self.client.userLeft(user, '#bots')
        signal.emit.assert_called_with('user_left', self.client, 'helga', '#bots')

    @patch('helga.comm.irc.IRCClient')
    def test_join_converts_from_unicode(self, irc):
        snowman = u'☃'
        bytes = '\xe2\x98\x83'
        self.client.join(snowman, snowman)
        irc.join.assert_called_with(self.client, bytes, key=bytes)

    @patch('helga.comm.irc.IRCClient')
    def test_leave_converts_from_unicode(self, irc):
        snowman = u'☃'
        bytes = '\xe2\x98\x83'
        self.client.leave(snowman, snowman)
        irc.leave.assert_called_with(self.client, bytes, reason=bytes)
