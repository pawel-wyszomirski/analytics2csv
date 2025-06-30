from flask import Flask, request, render_template_string, send_file, flash, redirect, url_for
import pandas as pd
import io
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def parse_ga_data(file_content):
    """Parsuje dane Google Analytics"""
    
    content = file_content.decode('utf-8')
    lines = content.split('\n')
    
    # 1. ZNAJDŹ DATĘ w linii typu "# Data rozpoczęcia: 20250628"
    date = None
    for line in lines:
        if 'Data rozpoczęcia:' in line:
            numbers = ''.join(c for c in line if c.isdigit())
            if len(numbers) >= 8:
                date_str = numbers[:8]
                date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                break
    
    if not date:
        from datetime import datetime
        date = datetime.now().strftime('%Y-%m-%d')
    
    result = {'Data': date}
    
    # 2. ZNAJDŹ WSZYSTKIE METRYKI
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # WSPÓŁCZYNNIK ODRZUCEŃ
        if line == "Współczynnik odrzuceń":
            if i + 1 < len(lines):
                value_line = lines[i + 1].strip()
                try:
                    result['Współczynnik_odrzuceń'] = float(value_line)
                except:
                    pass
            i += 2
            continue
        
        # TABELE Z PRZECINKAMI
        if ',' in line:
            parts = line.split(',')
            
            # Tabela: N-ty dzień,Opis metryki
            if len(parts) == 2 and parts[0] == "N-ty dzień":
                metric_name = parts[1].strip()
                
                if i + 1 < len(lines):
                    data_line = lines[i + 1].strip()
                    if ',' in data_line:
                        data_parts = data_line.split(',')
                        if len(data_parts) == 2 and data_parts[0] == "0000":
                            try:
                                value = float(data_parts[1])
                                
                                if 'Średni czas zaangażowania na aktywnego użytkownika' in metric_name:
                                    result['Średni_czas_zaangażowania_użytkownik'] = value
                                elif 'Średni czas zaangażowania na sesję' in metric_name:
                                    result['Średni_czas_zaangażowania_sesja'] = value
                                elif 'Sesje z zaangażowaniem na aktywnego użytkownika' in metric_name:
                                    result['Sesje_z_zaangażowaniem_użytkownik'] = value
                                elif 'Liczba aktywnych użytkowników dziennie/miesięcznie' in metric_name:
                                    result['Wskaźnik_aktywnych_użytkowników'] = value
                                    
                            except:
                                pass
                
                i += 2
                continue
            
            # Tabela: Nazwa wydarzenia,Liczba zdarzeń
            elif len(parts) == 2 and parts[0] == "Nazwa wydarzenia":
                i += 1
                
                while i < len(lines) and ',' in lines[i]:
                    event_line = lines[i].strip()
                    event_parts = event_line.split(',')
                    
                    if len(event_parts) == 2:
                        event_name = event_parts[0].strip()
                        try:
                            event_count = int(event_parts[1].strip())
                            
                            if event_name == 'page_view':
                                result['Wyświetlenia_stron'] = event_count
                            elif event_name == 'session_start':
                                result['Sesje'] = event_count
                            elif event_name == 'first_visit':
                                result['Nowi_użytkownicy'] = event_count
                            elif event_name == 'user_engagement':
                                result['Zaangażowanie_użytkowników'] = event_count
                            elif event_name == 'scroll':
                                result['Przewijania'] = event_count
                            elif event_name == 'click':
                                result['Kliknięcia'] = event_count
                                
                        except:
                            pass
                    
                    i += 1
                continue
            
            # Tabela: Identyfikator kraju,Aktywni użytkownicy  
            elif len(parts) == 2 and 'Identyfikator kraju' in parts[0] and 'Aktywni użytkownicy' in parts[1]:
                i += 1
                total_users = 0
                
                while i < len(lines) and ',' in lines[i]:
                    country_line = lines[i].strip()
                    country_parts = country_line.split(',')
                    
                    if len(country_parts) == 2:
                        try:
                            users = int(country_parts[1].strip())
                            total_users += users
                        except:
                            pass
                    
                    i += 1
                
                result['Aktywni_użytkownicy'] = total_users
                continue
            
            # Tabela: Tytuł strony i klasa ekranu,Wyświetlenia
            elif len(parts) == 2 and 'Tytuł strony i klasa ekranu' in parts[0] and 'Wyświetlenia' in parts[1]:
                i += 1
                total_views = 0
                
                while i < len(lines) and ',' in lines[i]:
                    page_line = lines[i].strip()
                    page_parts = page_line.split(',')
                    
                    if len(page_parts) >= 2:
                        try:
                            views = int(page_parts[-1].strip())
                            total_views += views
                        except:
                            pass
                    
                    i += 1
                
                if 'Wyświetlenia_stron' not in result:
                    result['Wyświetlenia_stron_suma'] = total_views
                continue
        
        i += 1
    
    return pd.DataFrame([result])

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Sprawdź czy plik został wgrany
        if 'file' not in request.files:
            flash('Nie wybrano pliku!')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Nie wybrano pliku!')
            return redirect(request.url)
        
        if file and file.filename.endswith('.csv'):
            try:
                # Przetwórz plik
                file_content = file.read()
                df = parse_ga_data(file_content)
                
                # Konwertuj do polskiego formatu
                df_polish = df.copy()
                for col in df_polish.columns:
                    if col != 'Data' and pd.api.types.is_numeric_dtype(df_polish[col]):
                        df_polish[col] = df_polish[col].astype(str).str.replace('.', ',')
                
                # Stwórz CSV do pobrania
                output = io.StringIO()
                df_polish.to_csv(output, index=False, sep=';')
                csv_content = output.getvalue()
                output.close()
                
                # Zapisz tymczasowo
                output_filename = f"converted_{secure_filename(file.filename)}"
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(csv_content)
                
                # Pokaż wyniki
                results = []
                for col in df.columns:
                    if col != 'Data':
                        results.append(f"{col}: {df[col].iloc[0]}")
                
                return render_template_string(RESULT_TEMPLATE, 
                                            filename=output_filename,
                                            date=df['Data'].iloc[0],
                                            metrics_count=len(df.columns)-1,
                                            results=results,
                                            table_html=df.to_html(classes='table table-striped', table_id='results'))
                
            except Exception as e:
                flash(f'Błąd przetwarzania pliku: {str(e)}')
                return redirect(request.url)
        else:
            flash('Proszę wgrać plik CSV!')
            return redirect(request.url)
    
    return render_template_string(INDEX_TEMPLATE)

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(filename, as_attachment=True, download_name=filename)
    except FileNotFoundError:
        flash('Plik nie został znaleziony!')
        return redirect(url_for('index'))

# HTML Templates
INDEX_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Konwerter Google Analytics</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .card { box-shadow: 0 10px 30px rgba(0,0,0,0.3); border: none; }
        .btn-primary { background: #ff6b35; border: none; }
        .btn-primary:hover { background: #e55a2b; }
    </style>
</head>
<body>
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-body text-center p-5">
                        <h1 class="card-title mb-4">🚀 Konwerter Google Analytics</h1>
                        <p class="card-text mb-4">Przekształć raport GA na jedną linię z kluczowymi metrykami</p>
                        
                        {% with messages = get_flashed_messages() %}
                            {% if messages %}
                                <div class="alert alert-danger" role="alert">
                                    {% for message in messages %}
                                        {{ message }}
                                    {% endfor %}
                                </div>
                            {% endif %}
                        {% endwith %}
                        
                        <form method="post" enctype="multipart/form-data">
                            <div class="mb-4">
                                <label for="file" class="form-label">Wybierz plik CSV z Google Analytics:</label>
                                <input type="file" class="form-control" id="file" name="file" accept=".csv" required>
                            </div>
                            <button type="submit" class="btn btn-primary btn-lg px-5">📊 Konwertuj</button>
                        </form>
                        
                        <div class="mt-4">
                            <small class="text-muted">
                                ✅ Wyciąga: współczynnik odrzuceń, sesje, scroll, click, czas zaangażowania<br>
                                🇵🇱 Polski format CSV (przecinki, średniki)
                            </small>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
'''

RESULT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wyniki Konwersji</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .card { box-shadow: 0 10px 30px rgba(0,0,0,0.3); border: none; }
        .btn-success { background: #28a745; border: none; }
        .btn-success:hover { background: #218838; }
    </style>
</head>
<body>
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-10">
                <div class="card">
                    <div class="card-body p-5">
                        <h1 class="card-title text-center mb-4">✅ Konwersja Zakończona!</h1>
                        
                        <div class="row mb-4">
                            <div class="col-md-4 text-center">
                                <h5>📅 Data</h5>
                                <p class="fw-bold">{{ date }}</p>
                            </div>
                            <div class="col-md-4 text-center">
                                <h5>📊 Metryki</h5>
                                <p class="fw-bold">{{ metrics_count }}</p>
                            </div>
                            <div class="col-md-4 text-center">
                                <h5>🇵🇱 Format</h5>
                                <p class="fw-bold">Polski CSV</p>
                            </div>
                        </div>
                        
                        <div class="text-center mb-4">
                            <a href="{{ url_for('download_file', filename=filename) }}" class="btn btn-success btn-lg px-5">
                                📥 Pobierz Plik CSV
                            </a>
                        </div>
                        
                        <h5>📈 Wyciągnięte Metryki:</h5>
                        <ul class="list-group mb-4">
                            {% for result in results %}
                                <li class="list-group-item">{{ result }}</li>
                            {% endfor %}
                        </ul>
                        
                        <div class="text-center">
                            <a href="{{ url_for('index') }}" class="btn btn-outline-primary">🔄 Konwertuj Kolejny Plik</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)