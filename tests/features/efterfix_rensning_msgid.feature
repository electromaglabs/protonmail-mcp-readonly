Feature: Message-ID, In-Reply-To och References kan inte smuggla dold text
  Som användare av en LLM som läser min e-post
  vill jag att identifierarna i ett mejl bara visas som de ASCII-<msg-id> de ska vara
  så att en avsändare inte kan gömma osynliga instruktioner i dem.

  Scenario Outline: Ett kodat ord med taggtecken i <rubrik> når inte modellen via get_email
    Given ett mejl där <rubrik> är "<x=?utf-8?b?TAGGAR?=@x.com>"
    When jag hämtar mejlet med get_email
    Then ska inget fält i svaret innehålla taggtecken
    And ska <fält> vara "<x=?utf-8?b?TAGGAR?=@x.com>"
    And ska suspicious_content nämna taggtecken

    Examples:
      | rubrik      | fält        |
      | Message-ID  | message_id  |
      | In-Reply-To | in_reply_to |
      | References  | references  |

  Scenario: Rå UTF-8 med taggtecken i Message-ID tas inte med
    Given ett mejl där Message-ID är rå UTF-8 med taggtecken
    When jag hämtar mejlet med get_email
    Then ska inget fält i svaret innehålla taggtecken
    And ska message_id vara tom
    And ska suspicious_content nämna taggtecken

  Scenario: En vanlig References-rubrik visas som msg-id:n
    Given ett mejl där References är "<a@x.se>\r\n <b@y.se>"
    When jag hämtar mejlet med get_email
    Then ska references vara "<a@x.se> <b@y.se>"
    And ska suspicious_content vara tom

  Scenario Outline: Taggtecken i <rubrik> når inte modellen via listningarna
    Given en tråd där startmejlets <rubrik> är "<x=?utf-8?b?TAGGAR?=@x.com>"
    When jag hämtar listningsraden
    Then ska inget fält i raden innehålla taggtecken
    And ska raden ha suspicious_content som nämner taggtecken

    Examples:
      | rubrik      |
      | Message-ID  |
      | In-Reply-To |
      | References  |
