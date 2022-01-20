def parse_form_fields(html_form, fields=None):
    # All fields sent through POST has a "name" set
    form_fields = html_form.select('[name]')
    # <select> and <textarea> does not have a "value" attribute
    if fields is None:
        fields = {}
    for form_field in form_fields:
        if form_field.name == 'input':
            if form_field['type'] == 'image':
                # Drop image button
                continue
            value = form_field.get('value', '')
        elif form_field.name == 'textarea':
            # The only textarea is the "comments" field (2021-04-24)
            value = ''
        elif form_field.name == 'select':
            # TODO: Check for "option" tag "DEFAULT" marker, if needed
            option = form_field.select_one('option')
            value = option.get('value', '')
        name = form_field['name']
        if name in fields:
            prev_value = fields[name]
            if isinstance(prev_value, list):
                prev_value.append(value)
            else:
                fields[name] = [prev_value, value]
        else:
            fields[name] = value
    return fields
