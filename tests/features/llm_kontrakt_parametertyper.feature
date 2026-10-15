Feature: Samma slags parameter beter sig likadant i alla verktyg
  Som modell som anropar verktygen
  vill jag att ett UID, en bilaga eller ett tal tas emot på samma sätt överallt
  så att ett anrop inte avvisas med ett engelskt valideringsfel i ett verktyg när det fungerar i ett annat.

  Scenario Outline: Ett UID som JSON-tal fungerar i alla verktyg som tar ett UID
    Given att det inte finns något mejl med UID 70
    When jag anropar <verktyg> med UID 70 som tal
    Then ska UID:t ha tagits emot som "70"

    Examples:
      | verktyg              |
      | get_email            |
      | get_email_headers    |
      | get_attachment       |
      | get_thread           |
      | reply_to_email       |
      | forward_email        |
      | create_reply_draft   |
      | create_forward_draft |
      | update_draft         |
      | send_draft           |
      | mark_email_read      |
      | flag_email           |

  Scenario Outline: En ensam bilaga kan anges som sträng
    When jag anropar <verktyg> med bilagan "rapport.pdf" som sträng
    Then ska bilagorna ["rapport.pdf"] ha lästs in

    Examples:
      | verktyg        |
      | send_email     |
      | reply_to_email |
      | forward_email  |

  Scenario Outline: Tal och sanningsvärden som sträng tas emot överallt
    When jag anropar <verktyg> med <parameter> satt till strängen "<värde>"
    Then ska anropet inte avvisas av valideringen

    Examples:
      | verktyg       | parameter    | värde |
      | search_emails | unseen       | true  |
      | search_emails | flagged      | true  |
      | search_emails | larger_than  | 1000  |
      | search_emails | max_results  | 10    |
      | list_emails   | page         | 2     |
      | get_thread    | max_messages | 10    |
