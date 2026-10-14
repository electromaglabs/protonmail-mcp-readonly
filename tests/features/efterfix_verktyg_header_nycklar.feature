Feature: get_email_headers använder samma nycklar som get_email
  Som en MCP-klient
  vill jag läsa message_id och reply_to med samma namn i båda verktygen
  eftersom verktygsbeskrivningen lovar de namnen och ett fel namn ger ett tomt värde.

  Scenario: Headers med bindestreck returneras med understreck
    Given att brevet med UID "7" i "Archive" har Message-ID "<abc@ex.se>" och Reply-To "svar@ex.se"
    When jag hämtar headers för brevet med UID "7" i "Archive"
    Then ska svaret ha message_id "<abc@ex.se>"
    And ska svaret ha reply_to "svar@ex.se"
    And ska inga nycklar i svaret innehålla bindestreck
