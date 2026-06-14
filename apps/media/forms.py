from django import forms

from .models import MediaAsset, MediaFolder


class MediaFolderForm(forms.ModelForm):
    class Meta:
        model = MediaFolder
        fields = ['name', 'parent']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'e.g. Campaign Assets'}),
            'parent': forms.Select(attrs={'class': 'input-field'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['parent'].queryset = MediaFolder.objects.filter(user=user)
            self.fields['parent'].empty_label = '— Root Folder —'
        self.fields['parent'].required = False


class MediaUploadForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ['file', 'folder', 'alt_text']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'input-field', 'accept': 'image/*,video/*,.pdf,.doc,.docx,.xls,.xlsx'}),
            'folder': forms.Select(attrs={'class': 'input-field'}),
            'alt_text': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Descriptive text for accessibility'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['folder'].queryset = MediaFolder.objects.filter(user=user)
            self.fields['folder'].empty_label = '— Root Folder —'
        self.fields['folder'].required = False
        self.fields['file'].required = True
